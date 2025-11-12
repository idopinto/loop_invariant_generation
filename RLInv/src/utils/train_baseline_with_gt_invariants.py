#!/usr/bin/env python3
"""
Script to capture unified baseline data from training dataset with UAutomizer.

This script:
1. Processes all .c files in dataset/training/programs (or specified directory)
2. Runs UAutomizer on each file with specified version (23, 24, 25, 26)
3. Captures timing information and attempts to extract invariants from witness files
4. Saves unified results to uautomizer{version}_train.json (contains both timing and invariants)

Command-line arguments:
    --uautomizer_version: UAutomizer version to use (23, 24, 25, or 26) [required]
    --timeout: Timeout in seconds for each verification (default: 600)
    --data_dir: Directory containing C files to process (default: dataset/training/programs)
    --limit: Limit the number of files to process (useful for testing)

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
import shutil
from pathlib import Path
from typing import Dict, List, Any, Tuple
from tqdm import tqdm

from src.utils.plain_verifier import run_uautomizer  
from src.utils.rewriter import Rewriter
from src.utils.program import Program
from pycparser import c_parser
root_dir = Path(__file__).parent.parent.parent
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


def check_correct_syntax(program_str: str) -> bool:
    """
    Check if the program has correct syntax.
    """
    parser = c_parser.CParser()
    try:
        parser.parse(program_str)
        return True
    except Exception:
        return False
    
    
def reformat(file_path: Path) -> Tuple[str, bool, bool]:
    """
    Reformat a C file with rewriter and checks if the file has target assertion and if the syntax is correct.
    Returns:
        Tuple[str, bool, bool]: The reformatted program string, True if the file has no target assertion, False if the syntax is incorrect.
    """
    r = Rewriter(file_path, rewrite=True)
    program = Program(r.lines_to_verify, r.replacement)
    no_target_assertion = False
    bad_syntax = False
    if len(program.assertions) == 0:
        no_target_assertion = True
        return "", no_target_assertion, bad_syntax
    target_assert = program.assertions[0] # assuming there is only one assertion in the program
    program_str= program.get_program_with_assertion(predicate=target_assert, 
                                                    assumptions=[],
                                                    assertion_points={},
                                                        forGPT=False)
    if not check_correct_syntax(program_str):
        bad_syntax = True
        return "", no_target_assertion, bad_syntax
    return program_str, no_target_assertion, bad_syntax

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
    # copy c_file to reports_dir
    shutil.copy(c_file, reports_dir / f"base_{c_file.name}")
    program_str, no_target_assertion, bad_syntax = reformat(c_file)
    program_path = reports_dir / f"reformatted_{c_file.stem}.c"
    no_invariants = False
    with open(program_path, "w") as f:
        f.write(program_str)
    if not no_target_assertion and not bad_syntax:
        result = {
            "file": c_file.name,
            "time": 0.0,
            "result": "UNKNOWN",
            "invariants": []
        }
        
        try:
            # Run UAutomizer
            # report1 = run_uautomizer(
            #     program_path=c_file,
            #     property_file_path=property_path,
            #     reports_dir=reports_dir,
            #     arch='32bit', 
            #     timeout_seconds=timeout_seconds,
            #     uautomizer_path=uautomizer_path
            # )
            # print(f"Report1: {report1.decision} {report1.time_taken}")
            report = run_uautomizer(
                program_path=program_path,
                property_file_path=property_path,
                reports_dir=reports_dir,
                arch='32bit', 
                timeout_seconds=timeout_seconds,
                uautomizer_path=uautomizer_path
            )
            print(f"Report: {report.decision} {report.time_taken}")
            
            result["time"] = report.time_taken
            result["result"] = report.decision
            
            if report.reports_dir:
                witness_yml = Path(report.reports_dir) / f"reformatted_{c_file.stem}_witness.yml"
                invariants = extract_invariants_from_witness(witness_yml)
                result["invariants"] = invariants
                if len(invariants) == 0:
                    no_invariants = True

        except Exception as e:
            print(f"Error processing {c_file.name}: {e}")
            result["result"] = "ERROR"
            result["error_message"] = str(e)
        
        return result, no_target_assertion, bad_syntax, no_invariants
    else:
        return None, no_target_assertion, bad_syntax, no_invariants


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
        default=root_dir / "dataset" / "training" / "orig_programs",
        help="Directory containing C files to be pre-processed (default: dataset/training/orig_programs)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of files to process (useful for testing). Processes first k files."
    )
    
    args = parser.parse_args()
    
    # Set up paths
    data_dir = Path(args.data_dir)
    print(f"Data directory: {data_dir}")
    # Find all C files
    c_files = list(data_dir.glob("*.c"))
    print(f"Found {len(c_files)} C files to process")
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
    output_dir = root_dir / "dataset" / "training" / f"uautomizer{args.uautomizer_version}_train"
    
    # # Check if output directory already exists
    # if output_dir.exists():
    #     print(f"Output directory already exists: {output_dir}")
    #     print("Exiting without processing.")
    #     sys.exit(0)
    
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    c_files_to_process = [c_file for c_file in c_files if not (reports_dir / c_file.stem).exists()]
    print(f"Found {len(c_files_to_process)} C files that have not been processed yet")
    results_file_path = output_dir / f"uautomizer{args.uautomizer_version}_train.json"
    if results_file_path.exists():
        with open(results_file_path, "r") as f:
            results = json.load(f)
    else:
        results = []
        
    bad_files_file_path = output_dir / f"uautomizer{args.uautomizer_version}_bad_files.json"
    if bad_files_file_path.exists():
        with open(bad_files_file_path, "r") as f:
            bad_files = json.load(f)
    else:
        bad_files = {"no_target_assertion": [], "bad_syntax": [], "with_error": [], "no_invariants": []}
    start_time = time.time()
    # Process files sequentially
    for c_file in tqdm(c_files_to_process, desc="Processing files"):
        c_file_report_dir = reports_dir / c_file.stem
        c_file_report_dir.mkdir(parents=True, exist_ok=True)
        result, no_target_assertion, bad_syntax, no_invariants = process_file(
            c_file=c_file,
            uautomizer_path=uautomizer_path,
            property_path=property_file,
            reports_dir=c_file_report_dir,
            timeout_seconds=args.timeout,
        )
        
        if result:
            entry = {
                "file": result["file"],
                "time": result["time"],
                "result": result["result"],
                "invariants": result["invariants"]
            }
            if "error_message" in result:
                entry["error_message"] = result["error_message"]
                bad_files["with_error"].append(c_file.name)
            if no_invariants:
                bad_files["no_invariants"].append(c_file.name)
            results.append(entry)
            # save results to file
            with open(results_file_path, "w") as f:
                json.dump(results, f, indent=2)
        if no_target_assertion:
            bad_files["no_target_assertion"].append(c_file.name)
        if bad_syntax:
            bad_files["bad_syntax"].append(c_file.name)
            # save bad files to file
        with open(bad_files_file_path, "w") as f:
            json.dump(bad_files, f, indent=2)
    
    total_time = time.time() - start_time
    
    # Save results file
    file_path = output_dir / f"uautomizer{args.uautomizer_version}_train.json"
    with open(file_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {file_path}")
    
    # Save bad files
    bad_files_file_path = output_dir / f"uautomizer{args.uautomizer_version}_bad_files.json"
    with open(bad_files_file_path, 'w') as f:
        json.dump(bad_files, f, indent=2)
    print(f"\nBad files saved to: {bad_files_file_path}")
    
    # Summary statistics
    print("\n=== Summary ===")
    if args.limit is not None:
        print(f"Total files available: {total_files}")
        print(f"Files processed: {len(c_files)} (limited by --limit={args.limit})")
        print(f"Bad files: {len(bad_files['no_target_assertion'])} no target assertion, {len(bad_files['bad_syntax'])} bad syntax")
    else:
        print(f"Total files available: {total_files}")
        print(f"Files processed: {len(c_files)}")
        print(f"Bad files: {len(bad_files['no_target_assertion'])} no target assertion, {len(bad_files['bad_syntax'])} bad syntax")
    print(f"Total time: {total_time:.2f} seconds")
    print(f"Average time per file: {total_time/len(c_files):.2f} seconds")

if __name__ == "__main__":
    main()

