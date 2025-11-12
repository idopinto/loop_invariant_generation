#!/usr/bin/env python3
"""
Script to capture unified baseline data from training dataset with UAutomizer.

This script:
1. Processes all .c files in dataset/training/programs (or specified directory)
2. Runs UAutomizer on each file with specified version (23, 24, 25, 26)
3. Captures timing information and attempts to extract invariants from witness files
4. Supports parallel processing for faster execution
5. Saves unified results to uautomizer{version}_train.json (contains both timing and invariants)

Command-line arguments:
    --uautomizer_version: UAutomizer version to use (23, 24, 25, or 26) [required]
    --timeout: Timeout in seconds for each verification (default: 600)
    --data_dir: Directory containing C files to process (default: dataset/training/programs)
    --limit: Limit the number of files to process (useful for testing)
    --workers: Number of parallel workers to use (default: 1, sequential processing)

The unified format is an array of objects, each containing:
{
    "file": "filename.c",
    "time": 12.34,
    "result": "TRUE",
    "invariants": [
        {"line": 10, "invariant": "x > 0"},
        ...
    ]
}

Results are saved to: dataset/training/uautomizer{version}_train/uautomizer{version}_train.json
Witness files and reports are saved to: dataset/training/uautomizer{version}_train/reports/
"""

import argparse
import json
import yaml
import sys
import time
import os
from pathlib import Path
from typing import Dict, List, Any, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from src.utils.plain_verifier import run_uautomizer  
root_dir = Path(__file__).parent.parent
verifier_executable_paths = {
    "23": root_dir / "tools" / "UAutomizer23" / "Ultimate.py",
    "24": root_dir / "tools" / "UAutomizer24" / "Ultimate.py",
    "25": root_dir / "tools" / "UAutomizer25" / "Ultimate.py",
    "26": root_dir / "tools" / "UAutomizer26" / "Ultimate.py",
}

# Property file path
property_file = root_dir / "dataset" / "properties" / "unreach-call.prp"

def extract_invariants_from_witness(witness_yml: Path) -> List[Dict[str, Any]]:
    """
    Extract invariants from UAutomizer witness.yml file.
    
    Pattern to match:
      - InvariantResult [Line: X]: Loop Invariant
        Derived loop invariant: <invariant_text>
    """
    invariants = []
    
    if not witness_yml.exists():
        return invariants

    try:
        with open(witness_yml, "r", encoding="utf-8", errors="ignore") as f:
            yml_data = yaml.safe_load(f)
        
        content = yml_data[0]['content']
        for invariant_dict in content:
            invariant = invariant_dict['invariant']
            if invariant.get('type') == 'loop_invariant':
                location = invariant.get('location')
                line = location.get('line')
                value = invariant.get('value')
                if line is not None and value is not None:
                    invariants.append({
                        "line": line,
                        "invariant": value
                    })
        return invariants
    except Exception as e:
        print(f"Warning: Could not extract invariants from {witness_yml}: {e}")
        return []


def process_file(
    c_file: Path,
    uautomizer_path: Path,
    property_path: Path,
    reports_dir: Path,
    timeout_seconds: int = 600,
) -> Dict[str, Any]:
    """
    Process a single C file with UAutomizer.
    
    Returns:
        Dictionary with timing and invariant information
    """
    result = {
        "file": c_file.name,
        "time": 0.0,
        "result": "UNKNOWN",
        "invariants": []
    }
    
    try:
        # Run UAutomizer
        report = run_uautomizer(
            program_path=c_file,
            property_file_path=property_path,
            reports_dir=reports_dir,
            arch='32bit', 
            timeout_seconds=timeout_seconds,
            uautomizer_path=uautomizer_path
        )
        
        result["time"] = report.time_taken
        result["result"] = report.decision
        
        if report.reports_dir:
            witness_yml = Path(report.reports_dir) / f"{c_file.stem}_witness.yml"
            invariants = extract_invariants_from_witness(witness_yml)
            result["invariants"] = invariants
        
    except Exception as e:
        print(f"Error processing {c_file.name}: {e}")
        result["result"] = "ERROR"
        result["error_message"] = str(e)
    
    return result


def process_file_wrapper(args_tuple: Tuple[Path, Path, Path, Path, int]) -> Dict[str, Any]:
    """
    Wrapper function for parallel processing.
    Takes a tuple of arguments to make it pickleable for ProcessPoolExecutor.
    """
    c_file, uautomizer_path, property_path, reports_dir, timeout_seconds = args_tuple
    return process_file(
        c_file=c_file,
        uautomizer_path=uautomizer_path,
        property_path=property_path,
        reports_dir=reports_dir,
        timeout_seconds=timeout_seconds,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Pre-process training dataset to get ground truth invariants"
    )
    parser.add_argument(
        "--uautomizer_version",
        type=str,
        required=True,
        choices=["23", "24", "25", "26"],
        help="UAutomizer version (23, 24, 25, or 26)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout in seconds for each verification (default: 600)"
    )
    parser.add_argument(
        "--data_dir",
        type=Path,
        default=root_dir / "dataset" / "training" / "programs",
        help="Directory containing C files to be pre-processed (default: dataset/training/programs)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of files to process (useful for testing). Processes first k files."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers to use (default: 1, sequential processing). "
             "Recommended: 1-2x CPU cores, but consider memory constraints."
    )
    
    args = parser.parse_args()
    
    # Validate workers argument
    if args.workers < 1:
        print(f"Error: --workers must be at least 1, got {args.workers}")
        sys.exit(1)
    
    cpu_count = os.cpu_count() or 1
    if args.workers > cpu_count * 2:
        print(f"Warning: Using {args.workers} workers but only {cpu_count} CPU cores available.")
        print(f"Consider using fewer workers (e.g., {cpu_count} or less) for better performance.")
    elif args.workers > cpu_count:
        print(f"Info: Using {args.workers} workers on {cpu_count} CPU cores. "
              f"This may cause context switching overhead.")
    
    # Set up paths
    data_dir = Path(args.data_dir)
    # Find all C files
    c_files = list(data_dir.glob("*.c"))
    uautomizer_path = verifier_executable_paths[args.uautomizer_version]    
    if not c_files:
        print(f"Error: No C files found in {data_dir}")
        sys.exit(1)
    
    # Limit number of files if specified
    total_files = len(c_files)
    if args.limit is not None:
        if args.limit <= 0:
            print(f"Error: --limit must be a positive integer, got {args.limit}")
            sys.exit(1)
        c_files = c_files[:args.limit]
        print(f"Found {total_files} C files total, processing first {len(c_files)} files (--limit={args.limit})")
    else:
        print(f"Found {len(c_files)} C files to process")
    print(f"UAutomizer version: {args.uautomizer_version}")
    print(f"UAutomizer path: {uautomizer_path}")
    print(f"Property file: {property_file}")
    print(f"Timeout: {args.timeout} seconds")
    if args.workers > 1:
        print(f"Parallel workers: {args.workers}")
    output_dir = root_dir / "dataset" / "training" / f"uautomizer{args.uautomizer_version}_train"
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Process files - unified format
    results = []
    start_time = time.time()
    
    # Prepare arguments for parallel processing
    process_args = []
    for c_file in c_files:
        c_file_report_dir = reports_dir / c_file.stem
        c_file_report_dir.mkdir(parents=True, exist_ok=True)
        process_args.append((
            c_file,
            uautomizer_path,
            property_file,
            c_file_report_dir,
            args.timeout,
        ))
    
    # Process files sequentially or in parallel
    if args.workers == 1:
        # Sequential processing
        for args_tuple in tqdm(process_args, desc="Processing files"):
            result = process_file_wrapper(args_tuple)
            entry = {
                "file": result["file"],
                "time": result["time"],
                "result": result["result"],
                "invariants": result["invariants"]
            }
            if "error_message" in result:
                entry["error_message"] = result["error_message"]
            results.append(entry)
    else:
        # Parallel processing
        print(f"Using {args.workers} parallel workers")
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            # Submit all tasks
            future_to_args = {
                executor.submit(process_file_wrapper, args_tuple): args_tuple
                for args_tuple in process_args
            }
            
            # Process completed tasks with progress bar
            for future in tqdm(as_completed(future_to_args), total=len(process_args), desc="Processing files"):
                try:
                    result = future.result()
                    entry = {
                        "file": result["file"],
                        "time": result["time"],
                        "result": result["result"],
                        "invariants": result["invariants"]
                    }
                    if "error_message" in result:
                        entry["error_message"] = result["error_message"]
                    results.append(entry)
                except Exception as e:
                    args_tuple = future_to_args[future]
                    c_file = args_tuple[0]
                    print(f"Error processing {c_file.name}: {e}")
                    results.append({
                        "file": c_file.name,
                        "time": 0.0,
                        "result": "ERROR",
                        "error_message": str(e),
                        "invariants": []
                    })
    
    total_time = time.time() - start_time
    
    # Save results file
    file_path = output_dir / f"uautomizer{args.uautomizer_version}_train.json"
    with open(file_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {file_path}")
    
    # Summary statistics
    print("\n=== Summary ===")
    if args.limit is not None:
        print(f"Total files available: {total_files}")
        print(f"Files processed: {len(c_files)} (limited by --limit={args.limit})")
    else:
        print(f"Total files processed: {len(c_files)}")
    print(f"Total time: {total_time:.2f} seconds")
    print(f"Average time per file: {total_time/len(c_files):.2f} seconds")

if __name__ == "__main__":
    main()

