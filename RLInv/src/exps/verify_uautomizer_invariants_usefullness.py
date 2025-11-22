import json
import time
from pathlib import Path
from typing import Dict
from tqdm import tqdm

from src.utils.program import Program
from src.utils.rewriter import Rewriter
from src.utils.predicate import Predicate
from src.eval.decision_procedure import DecisionProcedure
from src.utils.utils import save_as_json
from src.utils.paths import UAUTOMIZER_PATHS


def verify_uautomizer_invariants(
    json_file_path: str,
    uautomizer_version: str = "25",
    output_dir: str = "experiments/uautomizer_self_verification",
    timeout_seconds: float = 600.0,
    limit: int = None
):
    """
    Verify self-generated invariants from a JSON file using the same decision procedure as evaluate.py.
    
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
        data = data[:limit]
    
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
    
    for idx, entry in tqdm(enumerate(data), total=len(data), desc="Verifying invariants"):
        file_name = entry['file']
        rf_program = entry['rf_program']
        invariants = entry.get('invariants', [])
        
        print(f"\n--- Processing {idx+1}/{len(data)}: {file_name} with {len(invariants)} invariant(s) ---")
        
        # Create a working directory for this entry
        entry_dir = output_path / f"entry_{idx}_{Path(file_name).stem}"
        entry_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a temporary C file with the program code
        c_file_path = entry_dir / f"{Path(file_name).stem}.c"
        with open(c_file_path, 'w') as f:
            f.write(rf_program)
        
        # Create Program object using Rewriter (same as evaluate.py)
        rewriter = Rewriter(c_file_path, rewrite=True) # TODO: rewrite=False maybe
        program = Program(rewriter.lines_to_verify, rewriter.replacement)
        
        # Verify each invariant for this program
        invariant_results = []
        for inv_idx, inv_data in enumerate(invariants):
            line_number = inv_data['line']
            invariant_str = inv_data['invariant']
            
            print(f"  Invariant {inv_idx+1}/{len(invariants)} at line {line_number}: {invariant_str[:80]}...")
            
            # Create decision procedure for this invariant
            inv_dir = entry_dir / f"inv_{inv_idx}"
            inv_dir.mkdir(parents=True, exist_ok=True)
            
            # Create default property file (unreach-call.prp)
            property_file = inv_dir / "property.prp"
            with open(property_file, 'w') as f:
                f.write("CHECK( init(main()), LTL(G ! call(reach_error())) )")
            
            decision_procedure = DecisionProcedure(
                program=program,
                target_property_file_path=property_file,
                arch="32bit",  # Default architecture
                code_dir=inv_dir,
                uautomizer_path=uautomizer_path,
                timeout_seconds=timeout_seconds,
            )
            
            # Convert invariant string to Predicate object
            # Use the line_number from the data, or the beginning of loop from program
            invariant_predicate = Predicate(invariant_str, line_number)
            
            # Run verification (no model generation time)
            start_time = time.perf_counter()
            report = decision_procedure.run(invariant_predicate, model_gen_time=0.0)
            verification_time = time.perf_counter() - start_time
            
            inv_result = {
                'invariant_index': inv_idx,
                'line_number': line_number,
                'invariant': invariant_str,
                'report': report.to_dict(),
                'verification_time': verification_time,
            }
            invariant_results.append(inv_result)
            
            print(f"    Result: {report.final_decision} (Rule: {report.decision_rule})")
        
        entry_result = {
            'entry_index': idx,
            'file': file_name,
            'rf_program': rf_program,
            'original_result': entry.get('result'),
            'original_timings': entry.get('timings'),
            'num_invariants': len(invariants),
            'invariant_results': invariant_results
        }
        results['results'].append(entry_result)
    
    # Save results
    output_file = output_path / "verification_results.json"
    save_as_json(results, output_file)
    print("\n" + "="*80)
    print("Results saved to", output_file)
    print("="*80)
    
    # Print summary
    print_summary(results)
    
    return results


def print_summary(results: Dict):
    """Print a summary of verification results."""
    total_entries = results['total_entries']
    total_invariants = sum(r['num_invariants'] for r in results['results'])
    
    # Count decisions
    decision_counts = {}
    for entry in results['results']:
        for inv_result in entry['invariant_results']:
            decision = inv_result['report']['final_decision']
            decision_counts[decision] = decision_counts.get(decision, 0) + 1
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total entries processed: {total_entries}")
    print(f"Total invariants verified: {total_invariants}")
    print("\nDecision breakdown:")
    for decision, count in sorted(decision_counts.items()):
        percentage = (count / total_invariants * 100) if total_invariants > 0 else 0
        print(f"  {decision}: {count} ({percentage:.1f}%)")
    print("="*80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Verify UAutomizer self-generated invariants")
    parser.add_argument("json_file", type=str, help="Path to JSON file with programs and invariants")
    parser.add_argument("--uautomizer-version", type=str, default="25", help="UAutomizer version (default: 25)")
    parser.add_argument("--output-dir", type=str, default="experiments/uautomizer_self_verification", 
                       help="Output directory for results")
    parser.add_argument("--timeout", type=float, default=600.0, help="Verification timeout in seconds")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of entries to process")
    
    args = parser.parse_args()
    
    verify_uautomizer_invariants(
        json_file_path=args.json_file,
        uautomizer_version=args.uautomizer_version,
        output_dir=args.output_dir,
        timeout_seconds=args.timeout,
        limit=args.limit
    )

