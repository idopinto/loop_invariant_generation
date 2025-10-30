#!/usr/bin/env python3
"""
Script to evaluate multiple model results and generate a combined metrics table.

This script processes multiple model evaluation result files, calculates metrics for each,
and saves them in a combined CSV table in the experiments folder.
"""

import argparse
from pathlib import Path
from typing import List

from metrics import InvBenchMetrics, load_results


def find_model_result_files(results_dir: Path, pattern: str = "final_results_*.json") -> List[Path]:
    """Find all model result files matching the pattern."""
    return sorted(results_dir.glob(pattern))


def process_multiple_models(
    model_result_files: List[Path],
    baseline_file: Path,
    output_dir: Path,
    output_filename: str = None,
    include_model_generation_time: bool = False
) -> None:
    print(f"Loading baseline results from: {baseline_file}")
    baseline_results = load_results(baseline_file)
    inv_bench_metrics = InvBenchMetrics()
    
    timing_mode = "with model generation time" if include_model_generation_time else "without model generation time (verification only)"
    print(f"Calculating metrics {timing_mode}")

    print(f"\nProcessing {len(model_result_files)} model result files...")
    for i, model_file in enumerate(model_result_files, 1):
        print(f"\n[{i}/{len(model_result_files)}] Processing: {model_file.name}")
        try:
            model_results = load_results(model_file)
            if model_results is None or not isinstance(model_results, dict):
                print("  Warning: Invalid or empty results file, skipping")
                continue
            if "results" not in model_results or not model_results["results"]:
                print("  Warning: No valid results in file, skipping")
                continue
            model_name = model_results.get("model_path_or_name", "unknown_model")
            print(f"  Model: {model_name}")
            print(f"  Results: {len(model_results['results'])} tasks")
            inv_bench_metrics.add_model_with_timing_comparison(model_name, model_results, baseline_results, include_model_generation_time=include_model_generation_time)
            print("  ✓ Metrics calculated and added")
        except Exception as e:
            print(f"  ✗ Error processing {model_file.name}: {e}")

    print("\n" + "="*80)
    print("Combined Metrics Table:")
    print("="*80)
    inv_bench_metrics.print_table()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename
    inv_bench_metrics.save_results_to_csv(output_path)
    print(f"\n✓ Combined metrics saved to: {output_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate multiple model results and generate combined metrics table"
    )
    parser.add_argument(
        "--exp_id",
        type=str,
        required=True,
        help="Experiment ID"
    )
    parser.add_argument(
        "--data_split",
        type=str,
        required=True,
        choices=["easy", "hard"],
        help="Data split: easy or hard"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="final_results_*.json",
        help="Pattern to match model result files (default: final_results_*.json)"
    )
    parser.add_argument(
        "--include-model-generation-time",
        action="store_true",
        help="Include model generation time in speedup calculations (default: False, uses verification time only)"
    )
    
    args = parser.parse_args()
    
    root_dir = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv")
    experiments_dir = root_dir / "experiments" / f"exp_{args.exp_id}"
    baseline_file = root_dir / "dataset" / "evaluation" / args.data_split / "baseline_results.json"
    
    # Collect results from all per-model result directories: *_results/final_results_*.json
    model_result_files = sorted(experiments_dir.glob(f"*_results/{args.pattern}"))
    
    if not model_result_files:
        print("Error: No model result files found")
        print(f"  Searched in: {experiments_dir}/*_results")
        print(f"  Pattern: {args.pattern}")
        return
    
    experiments_dir.mkdir(parents=True, exist_ok=True)
    print(f"Found {len(model_result_files)} model result files:")
    for f in model_result_files:
        print(f"  - {f.name}")
    
    output_filename = f"metrics_exp_{args.exp_id}.csv"
    # Process all models
    process_multiple_models(
        model_result_files=model_result_files,
        baseline_file=baseline_file,
        output_dir=experiments_dir,
        output_filename=output_filename,
        include_model_generation_time=args.include_model_generation_time
    )


if __name__ == "__main__":
    main()

