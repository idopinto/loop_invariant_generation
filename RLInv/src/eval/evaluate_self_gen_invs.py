import json
from pathlib import Path
from tqdm import tqdm

from src.utils.program_new import Program
# from src.utils.rewriter import Rewriter
from src.utils.predicate import Predicate
from src.utils.utils import save_as_json
from src.utils.paths import UAUTOMIZER_PATHS, PROPERTIES_DIR

from src.utils.plain_verifier import run_uautomizer

ARCH = "32bit"
property_file_path = PROPERTIES_DIR / "unreach-call.prp"
def check_if_self_generated_invariants_are_useful(
    json_file_path: str,
    uautomizer_version: str = "25",
    output_dir: str = "experiments/uautomizer_self_verification_usefulness",
    timeout_seconds: float = 600,
    limit: int = None
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
    output_path = Path(output_dir).resolve()  # Convert to absolute path
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Limit data if specified
    if limit:
        data = data[1:limit]
    
    results = {
        'source_file': json_file_path,
        'total_entries': len(data),
        'uautomizer_version': uautomizer_version,
        'timeout_seconds': timeout_seconds,
        'results': []
    }
    
    print(f"Processing {len(data)} entries from {json_file_path}")
    print(f"Using UAutomizer version {uautomizer_version} at {uautomizer_path}")
    print("="*80)
    speedup_count = 0
    speedup_list = []
    for idx, entry in tqdm(enumerate(data), total=len(data)):
        file_name = entry['file']
        rf_program = entry['rf_program']
        invariants = entry.get('invariants', [])
        original_result = entry.get('result')
        baseline_timing = entry.get('timings').get('median')        
        entry_dir = output_path / f"{Path(file_name).stem}"
        entry_dir.mkdir(parents=True, exist_ok=True)

        for inv_idx, inv_data in tqdm(enumerate(invariants), total=len(invariants), desc="Verifying invariants"):
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
            print(f"TIMEOUT is {baseline_timing}")
            verifier_report = run_uautomizer(program_path=program_path, 
                                             property_file_path=property_file_path,
                                             reports_dir=inv_dir,
                                             arch=ARCH,
                                             timeout_seconds=baseline_timing,
                                             uautomizer_path=uautomizer_path)
            print(f"    Verifier report: {verifier_report.to_dict()}")
            speedup = baseline_timing / verifier_report.time_taken
            if verifier_report.decision == original_result and verifier_report.decision != "TIMEOUT" and speedup > 1.0:
                speedup_count += 1
                speedup_list.append(speedup)
            print(f"    Result: {verifier_report.decision} in {verifier_report.time_taken} seconds")
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
    print("\n" + "="*80)
    print("Results saved to", output_file)
    print("="*80)
    return results
    
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Check if self-generated invariants are useful")
    parser.add_argument("--json-file", type=str, help="Path to JSON file with programs and invariants")
    parser.add_argument("--uautomizer-version", type=str, default="25", help="UAutomizer version (default: 25)")
    parser.add_argument("--output-dir", type=str, default="experiments/uautomizer_self_verification", 
                       help="Output directory for results")
    parser.add_argument("--timeout", type=float, default=600.0, help="Verification timeout in seconds")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of entries to process")
    
    args = parser.parse_args()

    args.json_file = "dataset/training/uautomizer25_training_k1_rewrite/uautomizer25_training_k1_rewrite.json"
    args.output_dir = "experiments/uautomizer_self_verification_usefulness"
    args.timeout = 600
    args.limit = -1
    
    check_if_self_generated_invariants_are_useful(
        json_file_path=args.json_file,
        uautomizer_version=args.uautomizer_version,
        output_dir=args.output_dir,
        timeout_seconds=args.timeout,
        limit=args.limit
    )

