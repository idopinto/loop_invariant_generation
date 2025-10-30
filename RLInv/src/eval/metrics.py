#!/usr/bin/env python3
"""
Simple InvBench metrics calculation.

Calculates the four metrics from Table 2 (InvBench-Easy):
- % Correct Invariant: Percentage where invariant_correctness_report is Verified
- % Speedup: Percentage achieving speedup > 1
- Speedup>1: Average speedup over cases where speedup > 1
- Speedup_all: Average speedup across all instances
"""

import json
from pathlib import Path
from typing import Dict, List
import pandas as pd

class InvBenchMetrics:
    """Class-based interface for InvBench metrics calculation."""
    
    def __init__(self):
        self.model_metrics = pd.DataFrame(columns=["Model", "% Correct Invariant", "% Speedup", "Speedup>1", "Speedup_all"])
        self.baseline_results = []
    
    def add_model_with_timing_comparison(self, model_name: str, model_results: List[Dict], baseline_results: List[Dict], include_model_generation_time: bool = False):
        """Add model results and calculate metrics.
        
        Args:
            model_name: Name of the model
            model_results: Model evaluation results
            baseline_results: Baseline timing results
            include_model_generation_time: If True, use total_time_taken (includes model gen time).
                                          If False (default), use verification_time_taken (only verification).
        """
        self.baseline_results = baseline_results
        df = calculate_metrics(model_results, baseline_results, include_model_generation_time=include_model_generation_time)
        if self.model_metrics.empty:
            self.model_metrics = df
        else:
            self.model_metrics = pd.concat([self.model_metrics, df], ignore_index=True)
    
    def get_model_metrics(self, model_name: str) -> Dict[str, float]:
        """Get metrics for a specific model."""
        return self.model_metrics[self.model_metrics["Model"] == model_name]
    
    def print_table(self):
        """Print metrics table in Table 2 format."""
        print(self.model_metrics)
    
    def compare_with_paper_results(self):
        """Compare with paper results (placeholder)."""
        print("\nPaper Results Comparison:")
        print("Note: This is a placeholder for comparing with published results.")
        print("In a real implementation, you would load and compare with paper data.")
    
    def save_results_to_json(self, output_file: Path):
        """Save results to JSON file."""
        self.model_metrics.to_json(output_file, orient="records", lines=True)
            
    def save_results_to_csv(self, output_file: Path):
        """Save results to CSV file."""
        self.model_metrics.to_csv(output_file, index=False)


def calculate_metrics(model_full_results: dict, baseline_results: List[Dict], include_model_generation_time: bool = False) -> Dict[str, float]:
    """
    Calculate InvBench metrics for a model.
    
    Args:
        model_full_results: Full model evaluation results (DecisionProcedureReport format)
        baseline_results: List of baseline timing results
        include_model_generation_time: If True, use total_time_taken (includes model gen time).
                                       If False (default), use verification_time_taken (only verification).
    
    Returns:
        Dictionary with the four metrics
    """
    if not model_full_results:
        return pd.DataFrame(columns=["Model", "% Correct Invariant", "% Speedup", "Speedup>1", "Speedup_all"])
    model_name = model_full_results.get("model_path_or_name", "")
    model_results = model_full_results.get("results", [])
    
    # Create baseline lookups
    baseline_timing = {r["base_filename"]: r["baseline_timing"] for r in baseline_results}
    expected_verdict = {r["base_filename"]: str(r.get("expected_answer", "unknown")).lower() for r in baseline_results}
    # print(f"Baseline timing: {baseline_timing}")
    correct_count = 0
    speedup_count = 0
    speedups_gt1 = []
    all_speedups = []
    
    for result in model_results:
        # print(f"--------------------------------")
        # Check if invariant is correct (invariant_correctness_report is Verified)
        report = result.get("report", {})   
        correctness_report_decision = report.get("invariant_correctness_report", {}).get("decision")
        # print(f"Correctness report decision: {correctness_report_decision}")
        if correctness_report_decision == "Verified":
            correct_count += 1
        # Calculate speedup
        # task_name is already the YML file stem (matching baseline's base_filename)
        base_filename = result.get("task_name", "")
        # print(f"Base filename: {base_filename}")
        baseline_time = baseline_timing.get(base_filename, 0.0)
        # Use verification_time_taken by default (without model gen time), or total_time_taken if flag is set
        if include_model_generation_time:
            model_time = report.get("total_time_taken", 0.0)
        else:
            # Default: use verification time only (without model generation time)
            model_time = report.get("verification_time_taken", report.get("total_time_taken", 0.0))
        final_decision_raw = report.get("final_decision", "Unknown")
        # Map final_decision to boolean (true/false) for comparison with expected_verdict
        final_decision_bool = map_decision_to_boolean(final_decision_raw)
        expected = expected_verdict.get(base_filename, "unknown")
        # print(f"Baseline time: {baseline_time}")
        # print(f"Model time: {model_time}")
        # print(f"Final decision (raw): {final_decision_raw}, mapped to: {final_decision_bool}, expected: {expected}")
        # If baseline_time is 0 (no baseline timing available) or model_time is <= 0 (possibly failed/invalid model run),
        # set speedup = 1.0 as a neutral baseline, because a speedup ratio can't be computed in these cases.
        # This avoids division by zero and treats "no data" as "no improvement" for reporting purposes.
        # If decision is Unknown or does not match expected verdict, count as no-speedup
        invalid_for_speedup = (final_decision_bool == "unknown") or (expected != "unknown" and final_decision_bool != expected)

        if baseline_time == 0.0 or model_time <= 0 or invalid_for_speedup:
            speedup = 1.0
        else:
            speedup = baseline_time / model_time
        all_speedups.append(speedup)
        # print(f"Speedup: {speedup}")
        if speedup > 1.0:
            speedup_count += 1
            speedups_gt1.append(speedup)
    # print(f"--------------------------------")
    total_count = len(model_results)
    # print(f"Total count: {total_count}")
    # print(f"Correct count: {correct_count}")
    # print(f"Speedup count: {speedup_count}")
    # print(f"Speedups gt1: {speedups_gt1}")
    # print(f"All speedups: {all_speedups}")
    # return dataframe insted
    df = pd.DataFrame({
        "Model": [model_name],
        "% Correct Invariant": [correct_count / total_count],
        "% Speedup": [speedup_count / total_count],
        "Speedup>1": [sum(speedups_gt1) / len(speedups_gt1) if speedups_gt1 else 1.0],
        "Speedup_all": [sum(all_speedups) / len(all_speedups) if all_speedups else 1.0]
    })
    return df


def map_decision_to_boolean(decision: str) -> str:
    decision_lower = str(decision).lower()
    if decision_lower == "verified":
        return "true"
    elif decision_lower == "falsified":
        return "false"
    else:  # Unknown or any other value
        return "unknown"


def load_results(file_path: Path) -> List[Dict]:
    """Load results from JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def main():
    """Example usage."""
    # Load baseline results
    root_dir = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv")
    baseline_file = root_dir / "baseline_results" / "easy" / "baseline_results.json"
    baseline_results = load_results(baseline_file)
    print(f"Loaded {len(baseline_results)} baseline results")
    model_file = root_dir / "results" / "final_results_20251027_170908.json"
    model_results = load_results(model_file)
    model_name = model_results.get("model_path_or_name", "")
    
    print(f"Loaded {len(model_results)} model results ({model_name})")
    timestamp = model_results.get("evaluation_timestamp", "")
    invBenchMetrics = InvBenchMetrics()
    invBenchMetrics.add_model_with_timing_comparison(model_name, model_results, baseline_results)
    invBenchMetrics.print_table()
    invBenchMetrics.save_results_to_csv(root_dir / "results" / f"{model_name}_{timestamp}_metrics.csv")


if __name__ == "__main__":
    main()