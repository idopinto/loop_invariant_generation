from datetime import datetime
import json
from pathlib import Path
from tqdm import tqdm
from src.utils.utils import save_as_json
from src.utils.paths import UAUTOMIZER_PATHS, PROPERTIES_DIR

from src.utils.plain_verifier import run_uautomizer

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ARCH = "32bit"
property_file_path = PROPERTIES_DIR / "unreach-call.prp"
root_dir = Path(__file__).parent.parent.parent
experiments_dir = root_dir / "experiments"

# ANSI color codes: green for speedup, red for no speedup, orange for status
GREEN = "\033[92m"
RED = "\033[91m"
ORANGE = "\033[93m"
RESET = "\033[0m"


def check_if_self_gen_invariants_are_useful_togther(
    json_file_path: str,
    uautomizer_version: str = "25",
    output_dir: str = "uautomizer_self_verification_usefulness",
    timeout_seconds: float = 600,
    limit: int = None,
    timeout_is_baseline: bool = True,
):
    """
    Check if self-generated invariants are useful by verifying them with UAutomizer and checking the speedup.
    """
        # Load JSON data
    with open(json_file_path, 'r') as f:
        data = json.load(f)
    
    # Setup paths
    uautomizer_path = UAUTOMIZER_PATHS[uautomizer_version]
    unique_id = f"{output_dir}_{'baseline' if timeout_is_baseline else timeout_seconds}_{limit}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_path = experiments_dir / unique_id
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Limit data if specified
    if limit:
        data = data[:limit]
    
    results = {
        'source_file': str(json_file_path),
        'total_entries': len(data),
        'uautomizer_version': uautomizer_version,
        'timeout_seconds': timeout_seconds,
        "timeout_is_baseline": timeout_is_baseline,
        'results': [],
        "metrics": {
            "valid_speedup_count": 0,
            "valid_speedup_list": [],
            "valid_speedup_average": 0.0,
            "valid_speedup_percentage": 0.0
        }
    }

    logger.info(f"Processing {len(data)} entries from {json_file_path}")
    logger.info(f"Using UAutomizer version {uautomizer_version} at {uautomizer_path}")
    speedup_count = 0
    speedup_list = []
    for idx, entry in tqdm(enumerate(data), total=len(data)):
        file_name = entry['file']
        rf_program = entry['rf_program']
        invariants = entry.get('invariants', [])
        original_result = entry.get('result')
        entry_dir = output_path / f"{idx}_{Path(file_name).stem}"
        entry_dir.mkdir(parents=True, exist_ok=True)
        baseline_timing = entry.get('timings').get('median')
        split = entry.get('split')
        rf_program_lines = rf_program.split("\n")
        logger.info(f"Processing {file_name} with {len(invariants)} invariants")
        # Insert invariants from bottom to top (highest line number first)
        # This avoids having to track line number offsets
        sorted_invariants = sorted(invariants, key=lambda x: x['line'], reverse=True)
        for inv_data in sorted_invariants:
            invariant_str = inv_data['invariant']
            line_number = inv_data['line']
            rf_program_lines.insert(line_number, f"assume({invariant_str});")

        program_for_usefullness = "\n".join(rf_program_lines)
        program_path = entry_dir / "code_for_usefulness.c"
        with open(program_path, 'w') as out_file:
            out_file.write(program_for_usefullness)
        verifier_report = run_uautomizer(program_path=program_path, 
                                property_file_path=property_file_path,
                                reports_dir=entry_dir,
                                arch=ARCH,
                                timeout_seconds=baseline_timing if timeout_is_baseline else timeout_seconds,
                                uautomizer_path=uautomizer_path)
        speedup = baseline_timing / verifier_report.time_taken
        has_speedup = verifier_report.decision == original_result and verifier_report.decision != "TIMEOUT" and speedup > 1.0
        if has_speedup:
            speedup_count += 1
            speedup_list.append(speedup)
        

        color = GREEN if has_speedup else RED
        speedup_status = f"SPEEDUP x{speedup:.2f}" if has_speedup else f"NO SPEEDUP x{speedup:.2f}"
        logger.info(f"{color}{idx} | {file_name} | Split: {split} | Original result: {original_result} | # Invariants: {len(invariants)} | Result: {verifier_report.decision} | Time: {verifier_report.time_taken:.2f}s | Baseline: {baseline_timing:.2f}s | {speedup_status}{RESET}")
        current_avg = sum(speedup_list) / len(speedup_list) if speedup_list else 0.0
        logger.info(f"{ORANGE}    Status: Speedup count: {speedup_count}/{idx+1} | Current avg speedup: {current_avg:.2f}x{RESET}")
        
        invariant_result = {
            'file': file_name,
            'split': split,
            'original_result': original_result,
            'baseline_timing': baseline_timing,
            'invariants': invariants,
            'usefulness_report': verifier_report.to_dict(),
            'speedup': speedup,
            'has_speedup': has_speedup
        }
        results['results'].append(invariant_result)

    # Update metrics
    results['metrics']['valid_speedup_count'] = speedup_count
    results['metrics']['valid_speedup_list'] = speedup_list
    results['metrics']['valid_speedup_average'] = sum(speedup_list) / len(speedup_list) if speedup_list else 0.0
    results['metrics']['valid_speedup_percentage'] = speedup_count / len(data) * 100 if data else 0.0
    
    output_file = output_path / "verification_results.json"
    # logger.info(f"Results: {results}")
    save_as_json(results, output_file)
    logger.info(f"Results saved to {output_file}")
    return results


def check_if_self_generated_invariants_are_useful_seperately(
    json_file_path: str,
    uautomizer_version: str = "25",
    output_dir: str = "uautomizer_self_verification_usefulness",
    timeout_seconds: float = 600,
    limit: int = None,
    timeout_is_baseline: bool = True,
):
    """
    Check if self-generated invariants are useful by verifying them with UAutomizer and checking the speedup.
    
    Args:
        json_file_path: Path to JSON file containing programs and their invariants
        uautomizer_version: UAutomizer version to use (e.g., "25")
        output_dir: Directory to save results
        timeout_seconds: Timeout for verification
        limit: Maximum number of entries to process (None for all)
    """
    # Load JSON data
    with open(json_file_path, 'r') as f:
        data = json.load(f)
    
    # Setup paths
    uautomizer_path = UAUTOMIZER_PATHS[uautomizer_version]
    output_path = experiments_dir / output_dir
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Limit data if specified
    if limit:
        data = data[:limit]
    
    results = {
        'source_file': str(json_file_path),
        'total_entries': len(data),
        'uautomizer_version': uautomizer_version,
        'timeout_seconds': timeout_seconds,
        'results': []
    }
    
    logger.info(f"Processing {len(data)} entries from {json_file_path}")
    logger.info(f"Using UAutomizer version {uautomizer_version} at {uautomizer_path}")
    speedup_count = 0
    speedup_list = []
    for idx, entry in tqdm(enumerate(data), total=len(data)):
        file_name = entry['file']
        rf_program = entry['rf_program']
        invariants = entry.get('invariants', [])
        original_result = entry.get('result')
        baseline_timing = entry.get('timings').get('median')
        entry_dir = output_path / f"{idx}_{Path(file_name).stem}"
        entry_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Processing {file_name} with {len(invariants)} invariants")
        for inv_idx, inv_data in enumerate(invariants):
            rf_program_lines = rf_program.split("\n")
            invariant_str = inv_data['invariant']
            invariant_line_number = inv_data['line']
            rf_program_lines.insert(invariant_line_number, f"assume({invariant_str});")
            inv_dir = entry_dir / f"inv_{inv_idx}"
            inv_dir.mkdir(parents=True, exist_ok=True)
            
            program_for_usefullness = "\n".join(rf_program_lines)
        # print(f"    Program for usefulness: {program_for_usefullness}")
            program_path = inv_dir / f"inv_{inv_idx}_code_for_usefulness.c"
            with open(program_path, 'w') as out_file:
                out_file.write(program_for_usefullness)
            # print(f"TIMEOUT is {baseline_timing}")
            verifier_report = run_uautomizer(program_path=program_path, 
                                            property_file_path=property_file_path,
                                            reports_dir=inv_dir,
                                            arch=ARCH,
                                            timeout_seconds=baseline_timing if timeout_is_baseline else timeout_seconds,
                                            uautomizer_path=uautomizer_path)
            speedup = baseline_timing / verifier_report.time_taken
            has_speedup = verifier_report.decision == original_result and verifier_report.decision != "TIMEOUT" and speedup > 1.0
            if has_speedup:
                speedup_count += 1
                speedup_list.append(speedup)
            
            color = GREEN if has_speedup else RED
            speedup_status = f"SPEEDUP x{speedup:.2f}" if has_speedup else f"NO SPEEDUP x{speedup:.2f}"
            logger.info(f"{color}{file_name} [inv_{inv_idx}] Result: {verifier_report.decision} | Time: {verifier_report.time_taken:.2f}s | Baseline: {baseline_timing:.2f}s | {speedup_status}{RESET}")
            current_avg = sum(speedup_list) / len(speedup_list) if speedup_list else 0.0
            logger.info(f"{ORANGE}    Status: Speedup count: {speedup_count}/{idx*len(invariants)+inv_idx+1} | Current avg speedup: {current_avg:.2f}x{RESET}")
            invariant_result = {
                'file': file_name,
                'original_result': original_result,
                'baseline_timing': baseline_timing,
                'self_generated_invariant': invariant_str,
                'self_generated_invariant_line_number': invariant_line_number,
                'usefulness_report': verifier_report.to_dict(),
                'speedup': speedup
            }
            results['results'].append(invariant_result)

    results['valid_speedup_count'] = speedup_count
    results['valid_speedup_list'] = speedup_list
    results['valid_speedup_average'] = sum(speedup_list) / len(speedup_list) if speedup_list else 1.0
    results['valid_speedup_percentage'] = speedup_count / len(invariants) * 100 if invariants else 0.0
    output_file = output_path / "verification_results.json"
    save_as_json(results, output_file)
    logger.info(f"Results saved to {output_file}")
    return results
    
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Check if self-generated invariants are useful (togther or seperately)")
    parser.add_argument("--json-file", type=str, help="Path to JSON file with programs and invariants")
    parser.add_argument("--uautomizer-version", type=str, default="25", help="UAutomizer version (default: 25)")
    parser.add_argument("--output-dir", type=str, default="uautomizer_self_verification_usefulness", 
                       help="Output directory for results")
    parser.add_argument("--timeout", type=float, default=600.0, help="Verification timeout in seconds")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of entries to process")
    # parser.add_argument("--percentage", type=int, default=None, help="Percentage of entries to process")
    parser.add_argument("--seperate", action="store_true", help="For each entry, seperate the invariants and verify them separately, else verify all invariants together")
    parser.add_argument("--timeout-is-baseline", action="store_true", help="Timing is baseline timing, else it is specified timing")


    args = parser.parse_args()
    json_file = root_dir / args.json_file
    # json_file = root_dir / "dataset" / "training" / f"uautomizer{args.uautomizer_version}_training_k1_rewrite_" / f"uautomizer{args.uautomizer_version}_training_k1_rewrite_filtered.json"
    
    # args.output_dir = "uautomizer_self_verification_onfiltered"
    # args.timeout = 600
    logger.info(f"Running with arguments: {args}")
    if not args.seperate:
        check_if_self_gen_invariants_are_useful_togther(
            json_file_path=json_file,
            uautomizer_version=args.uautomizer_version,
            output_dir=args.output_dir,
            timeout_seconds=args.timeout,
            limit=args.limit,
            timeout_is_baseline=args.timeout_is_baseline
        )
    else:
        check_if_self_generated_invariants_are_useful_seperately(
            json_file_path=json_file,
            uautomizer_version=args.uautomizer_version,
            output_dir=args.output_dir,
            timeout_seconds=args.timeout,
            limit=args.limit,
            timeout_is_baseline=args.timeout_is_baseline
        )
    logger.info("Completed.")

