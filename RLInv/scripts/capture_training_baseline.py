#!/usr/bin/env python3
"""
Script to capture unified baseline data from training/clean dataset with UAutomizer.

This script:
1. Processes all .c files in dataset/training/clean
2. Runs UAutomizer on each file with specified version (23, 24, 25, 26)
3. Captures timing information and attempts to extract invariants
4. Saves unified results to baseline_v{version}.json (contains both timing and invariants)
5. Optionally saves separate timing.json and invariants.json for backward compatibility

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
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Any
from tqdm import tqdm

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.plain_verifier import run_uautomizer  # noqa: E402

# UAutomizer executable paths
verifier_executable_paths = {
    "23": project_root / "tools" / "UAutomizer23" / "Ultimate.py",
    "24": project_root / "tools" / "UAutomizer24" / "Ultimate.py",
    "25": project_root / "tools" / "UAutomizer25" / "Ultimate.py",
    "26": project_root / "tools" / "UAutomizer26" / "Ultimate.py",
}

# Property file path
property_file = project_root / "dataset" / "properties" / "unreach-call.prp"


def is_trivial_invariant(invariant_text: str) -> bool:
    """
    Check if an invariant is trivial or not learnable from source code.
    
    Filters out invariants that:
    - Are exactly "1" (true in C)
    - Reference variables that don't exist in the source code (e.g., "!(cond == 0)" 
      when cond is only a function parameter, not a program variable)
    """
    # Normalize whitespace for comparison
    normalized = invariant_text.strip()
    
    # Filter out trivial invariants
    trivial_patterns = [
        "1",                    # Always true
        "!(cond == 0)",        # References cond which doesn't exist as program variable
    ]
    
    return normalized in trivial_patterns


def extract_invariants_from_log(log_file_path: Path) -> List[Dict[str, Any]]:
    """
    Extract invariants from UAutomizer log file.
    
    Pattern to match:
      - InvariantResult [Line: X]: Loop Invariant
        Derived loop invariant: <invariant_text>
    """
    invariants = []
    
    if not log_file_path.exists():
        return invariants
    
    try:
        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # Look for InvariantResult pattern followed by Derived loop invariant
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Match: "  - InvariantResult [Line: X]: Loop Invariant"
            match = re.search(r'InvariantResult\s+\[Line:\s+(\d+)\]:\s+Loop Invariant', line)
            if match:
                line_num = int(match.group(1))
                
                # Look for the next line with "Derived loop invariant:"
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    # Match: "    Derived loop invariant: <text>"
                    invariant_match = re.search(r'Derived loop invariant:\s*(.+)', next_line)
                    if invariant_match:
                        invariant_text = invariant_match.group(1).strip()
                        # Clean up whitespace (replace multiple spaces/newlines with single space)
                        invariant_text = re.sub(r'\s+', ' ', invariant_text)
                        
                        # Filter out trivial invariants
                        if is_trivial_invariant(invariant_text):
                            i += 2  # Skip both lines but don't add to invariants
                            continue
                        
                        invariants.append({
                            "line": line_num,
                            "invariant": invariant_text
                        })
                        i += 2  # Skip both lines
                        continue
            
            i += 1
        
    except Exception as e:
        print(f"Warning: Could not extract invariants from {log_file_path}: {e}")
    
    return invariants


def process_file(
    c_file: Path,
    uautomizer_path: Path,
    property_path: Path,
    reports_dir: Path,
    timeout_seconds: int = 600,
    extract_invariants: bool = True
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
            arch='32bit',  # Default to 32bit, can be made configurable
            timeout_seconds=timeout_seconds,
            uautomizer_path=uautomizer_path
        )
        
        result["time"] = report.time_taken
        result["result"] = report.decision
        
        # Extract invariants from log file if requested
        if extract_invariants and report.log_file_path:
            log_path = Path(report.log_file_path)
            invariants = extract_invariants_from_log(log_path)
            result["invariants"] = invariants
        
    except Exception as e:
        print(f"Error processing {c_file.name}: {e}")
        result["result"] = "ERROR"
        result["error_message"] = str(e)
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Capture invariants.json and timing.json from training/clean dataset"
    )
    parser.add_argument(
        "--version",
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
        "--no-invariants",
        action="store_true",
        help="Skip invariant extraction (only capture timing)"
    )
    parser.add_argument(
        "--clean-dir",
        type=Path,
        default=project_root / "dataset" / "training" / "clean",
        help="Directory containing cleaned C files (default: dataset/training/clean)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for JSON files (default: same as clean-dir)"
    )
    parser.add_argument(
        "--separate-files",
        action="store_true",
        help="Also save separate timing.json and invariants.json files for backward compatibility"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of files to process (useful for testing). Processes first k files."
    )
    
    args = parser.parse_args()
    
    # Set up paths
    clean_dir = Path(args.clean_dir)
    base_output_dir = Path(args.output_dir) if args.output_dir else clean_dir
    
    # Create version-specific output directory (e.g., clean/23/ or output_dir/23/)
    output_dir = base_output_dir / args.version
    output_dir.mkdir(parents=True, exist_ok=True)
    
    uautomizer_path = verifier_executable_paths[args.version]
    
    # Validate paths
    if not clean_dir.exists():
        print(f"Error: Clean directory not found: {clean_dir}")
        sys.exit(1)
    
    if not uautomizer_path.exists():
        print(f"Error: UAutomizer not found: {uautomizer_path}")
        sys.exit(1)
    
    if not property_file.exists():
        print(f"Error: Property file not found: {property_file}")
        sys.exit(1)
    
    # Find all C files
    c_files = list(clean_dir.glob("*.c"))
    
    if not c_files:
        print(f"Error: No C files found in {clean_dir}")
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
    print(f"UAutomizer version: {args.version}")
    print(f"UAutomizer path: {uautomizer_path}")
    print(f"Property file: {property_file}")
    print(f"Timeout: {args.timeout} seconds")
    print(f"Extract invariants: {not args.no_invariants}")
    print(f"Output directory: {output_dir}")
    print()
    
    # Create reports directory for this run (inside version folder)
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Process files - unified format
    unified_results = []
    start_time = time.time()
    
    for c_file in tqdm(c_files, desc="Processing files"):
        result = process_file(
            c_file=c_file,
            uautomizer_path=uautomizer_path,
            property_path=property_file,
            reports_dir=reports_dir,
            timeout_seconds=args.timeout,
            extract_invariants=not args.no_invariants
        )
        
        # Create unified entry with both timing and invariants
        unified_entry = {
            "file": result["file"],
            "time": result["time"],
            "result": result["result"],
            "invariants": result["invariants"] if not args.no_invariants else []
        }
        
        # Add error message if present
        if "error_message" in result:
            unified_entry["error_message"] = result["error_message"]
        
        unified_results.append(unified_entry)
    
    total_time = time.time() - start_time
    
    # Save unified results file
    unified_file = output_dir / "baseline.json"
    with open(unified_file, 'w') as f:
        json.dump(unified_results, f, indent=2)
    print(f"\nUnified results saved to: {unified_file}")
    
    # Also save separate files for backward compatibility (optional)
    if args.separate_files:
        # Save timing.json (array format)
        timing_results = [
            {
                "file": r["file"],
                "time": r["time"],
                "result": r["result"]
            }
            for r in unified_results
        ]
        timing_file = output_dir / "timing.json"
        with open(timing_file, 'w') as f:
            json.dump(timing_results, f, indent=2)
        print(f"Timing results (separate) saved to: {timing_file}")
        
        # Save invariants.json (dictionary format)
        if not args.no_invariants:
            invariants_dict = {
                r["file"]: r["invariants"]
                for r in unified_results
            }
            invariants_file = output_dir / "invariants.json"
            with open(invariants_file, 'w') as f:
                json.dump(invariants_dict, f, indent=2)
            print(f"Invariants (separate) saved to: {invariants_file}")
            
            # Count files with invariants
            files_with_invariants = sum(1 for r in unified_results if r["invariants"])
            print(f"Files with invariants: {files_with_invariants}/{len(c_files)}")
    
    # Summary statistics
    print("\n=== Summary ===")
    if args.limit is not None:
        print(f"Total files available: {total_files}")
        print(f"Files processed: {len(c_files)} (limited by --limit={args.limit})")
    else:
        print(f"Total files processed: {len(c_files)}")
    print(f"Total time: {total_time:.2f} seconds")
    print(f"Average time per file: {total_time/len(c_files):.2f} seconds")
    
    # Decision summary
    decision_counts = {}
    for r in unified_results:
        decision = r["result"]
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    
    print("\nDecision summary:")
    for decision, count in sorted(decision_counts.items()):
        print(f"  {decision}: {count}")


if __name__ == "__main__":
    main()

