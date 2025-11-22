#!/usr/bin/env python3
"""
Simple InvBench metrics calculation.

Calculates the four metrics from Table 2 (InvBench-Easy):
- % Correct Invariant: Percentage where invariant_correctness_report is Verified
- % Speedup: Percentage achieving speedup > 1
- Speedup>1: Average speedup over cases where speedup > 1
- Speedup_all: Average speedup across all instances
"""

from pathlib import Path
from typing import Dict, List, Union
import pandas as pd
from src.utils.utils import load_json   
class InvBenchMetrics:
    """Class-based interface for InvBench metrics calculation."""
    
    def __init__(self):
        self.model_metrics = pd.DataFrame(columns=["Model", "% Correct Invariant", "% Speedup", "Speedup>1", "Speedup_all"])
        self.baseline_timings = []
    
    def add_model_with_timing_comparison(self, model_name: str, model_results: List[Dict], baseline: List[Dict], include_model_generation_time: bool = False):
        """Add model results and calculate metrics.
        
        Args:
            model_name: Name of the model
            model_results: Model evaluation results
            baseline: Baseline timing results
            include_model_generation_time: If True, use total_time_taken (includes model gen time).
                                          If False (default), use verification_time_taken (only verification).
        """
        # self.baseline_timing = baseline_timing
        df = calculate_metrics(model_name=model_name, model_results=model_results, baseline=baseline, include_model_generation_time=include_model_generation_time)
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


def calculate_metrics(model_name: str, model_results: Union[Dict, List[Dict]], baseline: List[Dict], include_model_generation_time: bool = False) -> pd.DataFrame:
    """
    Calculate InvBench metrics for a model.
    
    Args:
        model_name: Name of the model
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

    task_results = model_results.get("results", [])
    
    expected_verdict = {Path(r["file"]).stem: str(r.get("result", "UNKNOWN")).lower() for r in baseline}
    baseline_timing_lookup = {Path(r["file"]).stem: r["timings"]["median"] for r in baseline}
    
    for result in task_results:
        task_name = result.get("task_name", "")
        baseline_time = baseline_timing_lookup.get(task_name, 0.0)
        # print(f"Baseline time: {baseline_time}")
        report = result.get("report", {})        
        final_decision = report.get("final_decision", "UNKNOWN")
        
        # Check candidate invariant correctness
        correctness_invariant_report = report.get("invariant_correctness_report") or {}
        correctness_decision = correctness_invariant_report.get("decision", "UNKNOWN") if isinstance(correctness_invariant_report, dict) else "UNKNOWN"
        correct_count += 1 if correctness_decision == "TRUE" else 0
        
        # Get model timing (handle missing keys)
        if include_model_generation_time:
            model_timing = report.get("total_time_taken", 0.0)
        else:
            model_timing = report.get("verification_time_taken", report.get("total_time_taken", 0.0))
        # print(f"Model timing: {model_timing}")
        expected = expected_verdict.get(task_name, "unknown")
        invalid_for_speedup = (final_decision in {"UNKNOWN"}) or (expected != "unknown" and final_decision.lower() != expected)
        speedup = 1.0 if baseline_time == 0.0 or model_timing <= 0 or invalid_for_speedup else baseline_time / model_timing
        all_speedups.append(speedup)
        if speedup > 1.0:
            speedup_count += 1
            speedups_gt1.append(speedup)

    total_count = len(task_results) if task_results else 1
    
    df = pd.DataFrame({
        "Model": [model_name],
        "% Correct Invariant": [correct_count / total_count if total_count > 0 else 0.0],
        "% Speedup": [speedup_count / total_count if total_count > 0 else 0.0],
        "Speedup>1": [sum(speedups_gt1) / len(speedups_gt1) if speedups_gt1 else 1.0],
        "Speedup_all": [sum(all_speedups) / len(all_speedups) if all_speedups else 1.0]
    })
    return df


# def map_decision_to_boolean(decision: str) -> str:
#     decision_lower = str(decision).lower()
#     if decision_lower == "verified":
#         return "true"
#     elif decision_lower == "falsified":
#         return "false"
#     else:  # Unknown or any other value
#         return "unknown"


# def load_results(file_path: Path) -> List[Dict]:
#     """Load results from JSON file."""
#     with open(file_path, 'r') as f:
#         return json.load(f)


def main():
    """Example usage."""
    # Load baseline results
    root_dir = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv")
    baseline_file = root_dir / "dataset" / "easy" / "baseline_timing.json"
    baseline_results = load_json(file_path=baseline_file)
    print(f"Loaded {len(baseline_results)} baseline results")
    model_file = root_dir / "experiments" / "exp_1" / "model_results.json"
    model_results = load_json(file_path=model_file)
    model_name = model_results.get("model_path_or_name", "")
    
    print(f"Loaded {len(model_results)} model results ({model_name})")
    invBenchMetrics = InvBenchMetrics()
    invBenchMetrics.add_model_with_timing_comparison(model_name=model_name, model_results=model_results, baseline_timing=baseline_results, include_model_generation_time=False)
    invBenchMetrics.print_table()
    invBenchMetrics.save_results_to_csv(root_dir / "experiments" / "exp_1" / "metrics.csv")