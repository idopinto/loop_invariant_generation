#!/usr/bin/env python3
import argparse
import json
import yaml
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple
from tqdm import tqdm
from src.utils.plain_verifier import run_uautomizer  
from src.utils.rewriter import Rewriter
from src.utils.program import Program
from src.utils.utils import write_file
from pycparser import c_parser
from src.utils.baseline_utils import get_verifier_version, get_system_info, get_runtime_configuration
from src.utils.paths import DATASET_DIR, UAUTOMIZER_PATHS, PROPERTIES_DIR
import statistics

property_file_path = PROPERTIES_DIR / "unreach-call.prp"
ARCH = "32bit"
DIFFICULTY_THRESHOLD = 30

def extract_invariants_from_log(log_file: Path) -> List[Dict[str, Any]]:
    """
    Extract invariants from UAutomizer log file.
    """
    try:
        invariants = []
        with open(log_file, "r", encoding="utf-8", errors="ignore") as logf:
            for line in logf:
                if "InvariantResult [Line:" in line:
                    idx1 = line.find("InvariantResult [Line:")
                    idx2 = line.find("]:", idx1)
                    if idx1 != -1 and idx2 != -1:
                        try:
                            line_num_str = line[idx1 + len("InvariantResult [Line:"):idx2]
                            line_num = int(line_num_str.strip())
                        except Exception:
                            continue
                        next_line = next(logf, None)
                        if next_line is not None:
                            invariant_tag = "Derived loop invariant:"
                            inv_idx = next_line.find(invariant_tag)
                            if inv_idx != -1:
                                inv_val = next_line[inv_idx + len(invariant_tag):].strip()
                                if inv_val:
                                    invariants.append({
                                        "line": line_num,
                                        "invariant": inv_val
                                    })
        return invariants
    except Exception as e:
        print(f"Warning: Could not extract invariants from {log_file}: {e}")
        return []   

def extract_invariants_from_witness(witness_yml: Path) -> List[Dict[str, Any]]:
    """
    Extract invariants from UAutomizer witness.yml file.
    
    Pattern to match:
      - InvariantResult [Line: X]: Loop Invariant
        Derived loop invariant: <invariant_text>
    """
    try:
        invariants = []
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
    Check if the program has correct C syntax.
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
    r = Rewriter(file_path)
    program = Program(r.lines_to_verify, r.replacement)
    problems = {
        "no_target_assertion": False,
        "multiple_target_assertions": False,
        "bad_syntax": False,
        "no_invariants": False,
    }
    if len(program.assertions) == 0:
        problems["no_target_assertion"] = True
        return "", problems
    if len(program.assertions) > 1:
        problems["multiple_target_assertions"] = True
        return "", problems
    target_assert = program.assertions[0] # assuming there is only one assertion in the program
    program_str= program.get_program_with_assertion(predicate=target_assert, 
                                                    assumptions=[],
                                                    assertion_points={},
                                                    forGPT=False)
    if not check_correct_syntax(program_str):
        problems["bad_syntax"] = True
        return "", problems
    return program_str, problems


def process_file(
    c_file: Path,
    uautomizer_path: Path,
    reports_dir: Path = None,
    timeout_seconds: float = 600.0,
    k: int = 1,
    rewrite: bool = False,
) -> Dict[str, Any]:
    """
    Process a single C file with UAutomizer.
    
    Returns:
        Dictionary with timing and invariant information
    """
    orig_program_str = open(c_file, "r").read()
    base_program_path = reports_dir / f"base_{c_file.stem}.c"
    write_file(base_program_path, orig_program_str)
    rf_program_str, rf_problems = reformat(c_file)
    rf_program_path = reports_dir / f"rf_{c_file.stem}.c"
    write_file(rf_program_path, rf_program_str)
    result = {
            "file": c_file.name,
            "orig_program": orig_program_str,
            "rf_program": rf_program_str,
            "result": "UNKNOWN",
            "reason": "",
            "timings": {
                "all": [],
                "average": 0.0,
                "median": 0.0
            },
    }
    if not rf_problems["no_target_assertion"] and not rf_problems["bad_syntax"]:
        try:
            decision_time = {}
            for i in tqdm(range(k), desc="Running UAutomizer", leave=False):
                program_to_verify = rf_program_path if rewrite else base_program_path
                print("Verifying the program: ", program_to_verify)
                report = run_uautomizer(
                    program_path=program_to_verify,
                    property_file_path=property_file_path,
                    reports_dir=reports_dir,
                    timeout_seconds=timeout_seconds,
                    uautomizer_path=uautomizer_path,
                    arch=ARCH
                )
                decision_time[report.time_taken] = report.decision
                print(f"Report: {report.decision} ({report.decision_reason}) in {report.time_taken} seconds")
                result["timings"]["all"].append(report.time_taken)
                # last_report = report
            result["timings"]["average"] = statistics.mean(result["timings"]["all"])
            result["timings"]["median"] = statistics.median(result["timings"]["all"])
            # {600: TIMEOUT, 550: TRUE, 600: TIMEOUT} -> median
            print(f"Decision time dict: {decision_time}")
            if result["timings"]["median"] < timeout_seconds:
                result["result"] = decision_time[result["timings"]["median"]]
            else:
                result["result"] = "TIMEOUT"
            # result["time"] = report.time_taken
            # result["result"] = report.decision
            result["reason"] = report.decision_reason
            
            if report.reports_dir:
                # Extracting the invariant only from the last verifier run.
                witness_yml = Path(report.reports_dir) / f"{'rf' if rewrite else 'base'}_{c_file.stem}_witness.yml"
                if not witness_yml.exists(): # if the witness file does not exist, then we need to extract the invariants from the log file happens with UAutomizer23
                    log_file = Path(report.reports_dir) / f"{'rf' if rewrite else 'base'}_{c_file.stem}.log"
                    invariants = extract_invariants_from_log(log_file)
                    result["invariants"] = invariants
                else:
                    invariants = extract_invariants_from_witness(witness_yml)
                    result["invariants"] = invariants

        except Exception as e:
            print(f"Error processing {c_file.name}: {e}")
            result["result"] = "ERROR"
            result["reason"] += " | " + str(e)
        
    else:
        if rf_problems["no_target_assertion"]:
            result["reason"] += " | no_target_assertion"
        if rf_problems["multiple_target_assertions"]:
            result["reason"] += " | multiple_target_assertions"
        if rf_problems["bad_syntax"]:
            result["reason"] += " | bad_syntax"
    return result

def get_c_files(data_dir: Path, reports_dir: Path, limit: int = -1, prefix: str = "") -> List[Path]:
    """
    Get all C files in the data directory.
    """
    c_files = list(data_dir.glob(f"{prefix}*.c"))
    if not c_files:
        print(f"Error: No C files found in {data_dir}")
        sys.exit(1)
    total_files = len(c_files)
    if limit >= 0:
        c_files = c_files[:limit]
        print(f"Found {total_files} C files total, processing first {len(c_files)} files (--limit={limit})")

    c_files_to_process = [c_file for c_file in c_files if not (reports_dir / c_file.stem).exists()]
    print(f"Found {len(c_files_to_process)} C files that have not been processed yet.")
    return c_files_to_process

def load_data_checkpoint(results_file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
    if results_file_path.exists():
        return json.load(open(results_file_path, "r"))
    else:
        return []

def run_baseline(args: argparse.Namespace) -> None:
    data_dir = DATASET_DIR / args.dataset_type / "orig_programs"
    uautomizer_path = UAUTOMIZER_PATHS[args.uautomizer_version]
    folder_name = f"uautomizer{args.uautomizer_version}_{args.dataset_type}_k{args.k}_{'rewrite' if args.rewrite else 'no_rewrite'}_"
    output_dir = DATASET_DIR / args.dataset_type / folder_name
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    c_files_to_process = get_c_files(data_dir, reports_dir, args.limit, args.prefix)
    results_file_path = output_dir / f"{folder_name}.json"
    results = load_data_checkpoint(results_file_path)

    start_time = time.time()
    for c_file in tqdm(c_files_to_process, desc="Processing files"):
        c_file_report_dir = reports_dir / c_file.stem
        c_file_report_dir.mkdir(parents=True, exist_ok=True)
        result = process_file(
            c_file=c_file,
            uautomizer_path=uautomizer_path,
            reports_dir=c_file_report_dir,
            timeout_seconds=args.timeout,
            k=args.k,
            rewrite=args.rewrite
        )
        if result:
            median_time = result["timings"]["median"]
            result["split"] = "easy" if median_time <= DIFFICULTY_THRESHOLD else "hard"
            results.append(result)
            with open(results_file_path, "w") as f:
                json.dump(results, f, indent=2)
    total_time = time.time() - start_time
    metadata_output_path = output_dir / f"{folder_name}_metadata.json"
    save_metadata(output_path=metadata_output_path,
                  uautomizer_path=uautomizer_path,
                  timeout_seconds=args.timeout, 
                  total_time=total_time, 
                  total_programs=len(results),
                  k=args.k,
                  dataset_type=args.dataset_type)
    return results

def parse_args():
    parser = argparse.ArgumentParser(
        description="Baseline data collection from training or evaluation dataset."
    )
    parser.add_argument(
        "--dataset_type",
        type=str,
        required=True,
        choices=["training", "evaluation"],
        help="Dataset type (train or eval)"
    )

    parser.add_argument(
        "--uautomizer_version",
        type=str,
        default="25",
        choices=["23", "24", "25", "26"],
        help="UAutomizer version (23, 24, 25, or 26)"
    )
    parser.add_argument(
        "--k",
        type=int,
        default=1,
        help="Number of times to run UAutomizer for each file (default: 1)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Timeout in seconds for each verification (default: 600.0)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=-1,
        help="Limit the number of files to process (useful for testing). Processes first k files."
    )
    parser.add_argument(
        "--rewrite",
        action="store_true",
        help="Rewrite the programs before running UAutomizer"
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="",
        help="Filter files by prefix"
    )
    return parser.parse_args()

def save_metadata(output_path: Path, uautomizer_path: Path, timeout_seconds: float, total_time: float, total_programs: int, k: int, dataset_type: str):
    # try to load metadata
    if output_path.exists():
        old_metadata = json.load(open(output_path, "r"))
        old_total_time = old_metadata["total_time"]
    else:
        old_total_time = 0.0
    verifier_versions = get_verifier_version(uautomizer_path)
    system_info = get_system_info()
    detected_config = get_runtime_configuration(uautomizer_path)
    configuration = {
        "uautomizer_java_heap_max_gb": detected_config.get('uautomizer_java_heap_max_gb'),
        "slurm_cpus_per_task": detected_config.get('slurm_cpus_per_task'),
        "slurm_memory_gb": detected_config.get('slurm_memory_gb')
    }
    metadata = {
        "verifier_versions": verifier_versions,
        "system_info": system_info,
        "configuration": configuration,
        "k": k,
        "total_programs": total_programs,
        "total_time": old_total_time + total_time,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dataset_type": dataset_type,
        "timeout_seconds": timeout_seconds
    }
    try:
        with open(output_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"\nMetadata saved successfully to: {output_path}")
    except Exception as e:
        print(f"\nERROR: Failed to save metadata to {output_path}: {e}")
        raise
    
def main():
    args = parse_args()
    print(f"Running baseline with the following arguments:\n{args}")
    run_baseline(args)


if __name__ == "__main__":
    main()

