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
from typing import Dict, List, Union
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


def calculate_metrics(model_results: Union[Dict, List[Dict]], baseline_timing: List[Dict], include_model_generation_time: bool = False) -> pd.DataFrame:
    """
    Calculate InvBench metrics for a model.
    
    Args:
        model_results: Either a dict with "results" key containing list of task results,
                      or a list of task result dicts directly
        baseline_timing: List of baseline timing results
        include_model_generation_time: If True, use total_time_taken (includes model gen time).
                                       If False (default), use verification_time_taken (only verification).
    
    Returns:
        DataFrame with the four metrics
    """
    if not model_results:
        return pd.DataFrame(columns=["Model", "% Correct Invariant", "% Speedup", "Speedup>1", "Speedup_all"])
    
    # Initialize accumulators
    all_speedups = []
    speedup_count = 0
    speedups_gt1 = []
    correct_count = 0
    
    # Create baseline lookups (preserve original list for expected_verdict)
    baseline_timing_dict = {r["file"]: r["time"] for r in baseline_timing}
    expected_verdict = {r["file"]: str(r.get("result", "unknown")).lower() for r in baseline_timing}
    
    # Handle different input formats: dict with "results" key or list of results
    if isinstance(model_results, dict):
        # If it's a dict, extract model name and results list
        model_name = model_results.get("model_path_or_name", "unknown_model")
        task_results = model_results.get("results", [])
    elif isinstance(model_results, list):
        # If it's a list, use it directly as task results
        task_results = model_results
        # Try to get model name from first result if available
        model_name = "unknown_model"
        if task_results and isinstance(task_results[0], dict):
            model_name = task_results[0].get("model_path_or_name", "unknown_model")
    else:
        # Invalid input type
        return pd.DataFrame(columns=["Model", "% Correct Invariant", "% Speedup", "Speedup>1", "Speedup_all"])
    
    # Iterate over all task results
    for result in task_results:
        # Extract task information
        if isinstance(result, dict):
            task_name = result.get("task_name", "")
            report = result.get("report", {})
            
            # Check invariant correctness
            invariant_report = report.get("invariant_correctness_report", {})
            if isinstance(invariant_report, dict):
                correctness_decision = invariant_report.get("decision", "")
                if isinstance(correctness_decision, dict):
                    correctness_decision = correctness_decision.get("name", "")
                if str(correctness_decision).lower() == "verified":
                    correct_count += 1
            
            # Get baseline time for this task
            baseline_time = baseline_timing_dict.get(task_name, 0.0)
            
            # Get model time (verification or total)
            if include_model_generation_time:
                model_time = report.get("total_time_taken", 0.0)
            else:
                model_time = report.get("verification_time_taken", report.get("total_time_taken", 0.0))
            
            # Get final decision
            final_decision_raw = report.get("final_decision", "Unknown")
            if isinstance(final_decision_raw, dict):
                final_decision_raw = final_decision_raw.get("name", "Unknown")
            
            # Map final_decision to boolean (true/false) for comparison with expected_verdict
            final_decision_bool = map_decision_to_boolean(str(final_decision_raw))
            expected = expected_verdict.get(task_name, "unknown")
            invalid_for_speedup = (final_decision_bool == "unknown") or (expected != "unknown" and final_decision_bool != expected)
            
            # Calculate speedup
            if baseline_time == 0.0 or model_time <= 0 or invalid_for_speedup:
                speedup = 1.0
            else:
                speedup = baseline_time / model_time
            
            all_speedups.append(speedup)
            if speedup > 1.0:
                speedup_count += 1
                speedups_gt1.append(speedup)
    
    total_count = len(task_results) if task_results else 1
    
    # Create DataFrame with metrics
    df = pd.DataFrame({
        "Model": [model_name],
        "% Correct Invariant": [correct_count / total_count if total_count > 0 else 0.0],
        "% Speedup": [speedup_count / total_count if total_count > 0 else 0.0],
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