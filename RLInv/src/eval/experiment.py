from typing import List, Optional, Dict, Any
import subprocess
import sys
import csv
from pathlib import Path
from dataclasses import dataclass, field
from src.eval.evaluate import InvBenchEvaluator
from src.utils.utils import load_dataset
from src.eval.model import Model
from src.eval.evaluate import InvBenchEvaluatorConfig
import argparse
from src.eval.metrics import InvBenchMetrics
from src.utils.utils import load_json, _sanitize

@dataclass
class ExperimentConfig:
    root_dir: Path = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv")
    exp_id: str = "exp_1"
    data_split: str = "easy" # "easy", "hard", "single", "unknowns", "full"
    models: List[str] = field(default_factory=lambda: ["gpt-oss-20b"])
    limit: int = -1
    default_timeout_seconds: int = 600
    property_kind: str = "unreach"
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    uautomizer_version: str = "uautomizer23"  # uautomizer23, uautomizer24, uautomizer25, uautomizer26


def load_baseline_timing_csv(file_path: Path) -> Optional[List[Dict[str, Any]]]:
    """
    Load baseline timing from CSV file and convert to list of dicts format.
    
    CSV format: file,result,time
    Returns: List of dicts with 'file', 'result', 'time' keys (same format as JSON)
    """
    if not file_path.exists():
        return None
    
    try:
        baseline_timing = []
        with open(file_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert time to float
                baseline_timing.append({
                    'file': row.get('file', ''),
                    'result': row.get('result', ''),
                    'time': float(row.get('time', 0))
                })
        return baseline_timing if baseline_timing else None
    except Exception as e:
        print(f"Error loading CSV from {file_path}: {e}")
        return None


class EvalExperiment:
    def __init__(self,config: ExperimentConfig):
        self.config = config 
        self.root_dir = self.config.root_dir
        self.data_root = self.root_dir / "dataset" / "evaluation" / "full"
        self.setup()
        
    def setup(self):
        # Extract version number from uautomizer_version (e.g., "uautomizer23" -> "23")
        self.version_number = self.config.uautomizer_version.replace("uautomizer", "")
        self.dataset_path = self.data_root / self.version_number / self.config.data_split / "yml"
        self.baseline_file_csv = self.data_root / self.version_number / f"baseline_timing{self.version_number}.csv"
        self.experiments_dir = self.root_dir / "experiments" / f"exp_{self.config.exp_id}"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_timing = self.get_baseline_timing()
        self.tasks = load_dataset(dataset_path=self.dataset_path, 
                                  property_kind=self.config.property_kind, 
                                  limit=self.config.limit,
                                  prefix=self.config.prefix,
                                  suffix=self.config.suffix)
        self.inv_bench_metrics_without_gen_time = InvBenchMetrics()
        self.inv_bench_metrics_with_gen_time = InvBenchMetrics()
        self.model_result_files = []
    
    def get_baseline_timing(self):
        # Try CSV format first (new format)
        baseline_timing = load_baseline_timing_csv(file_path=self.baseline_file_csv)
        
        if baseline_timing is None or len(baseline_timing) == 0:
            # Run baseline script via subprocess
            eval_dir = self.data_root / self.version_number / self.config.data_split
            baseline_script = self.root_dir / "src" / "eval" / "baseline.py"
            print(f"Baseline results not found. Running baseline evaluation for {self.config.data_split} split...")
            print(f"Using UAutomizer version: {self.config.uautomizer_version}")
            response = input("Baseline results not found. Run baseline evaluation? (y/n): ")
            if response == "y":
                cmd = [
                    sys.executable, 
                    str(baseline_script),
                    str(eval_dir),
                    "--uautomizer_version", self.config.uautomizer_version,
                    "--timeout", str(self.config.default_timeout_seconds)
                ]
                # Add --do-split flag for full dataset
                if self.config.data_split == "full":
                    cmd.append("--do-split")
                
                subprocess.run(cmd, check=True)
                # Try loading CSV first, then JSON
                baseline_timing = load_baseline_timing_csv(file_path=self.baseline_file_csv)
                if baseline_timing is None or len(baseline_timing) == 0:
                    baseline_timing = load_json(file_path=self.baseline_file_json)
                if baseline_timing is None or len(baseline_timing) == 0:
                    # Try old location as fallback
                    baseline_timing = load_json(file_path=self.baseline_file_old)
                print(f"Baseline evaluation completed. Loaded {len(baseline_timing) if baseline_timing else 0} baseline timing.")
        else:
            if self.baseline_file_csv.exists():
                print(f"Baseline results found in CSV: {self.baseline_file_csv}")
            elif self.baseline_file_json.exists():
                print(f"Baseline results found in JSON: {self.baseline_file_json}")
            else:
                print(f"Baseline results found in: {self.baseline_file_old}")
        return baseline_timing
            
    def run(self):
        self.get_baseline_timing()
        for model_path_or_name in self.config.models:
            working_dir = self.experiments_dir / f"{_sanitize(model_path_or_name)}"
            model = Model(model_path_or_name=model_path_or_name)
            inv_bench_evaluator_config = InvBenchEvaluatorConfig(
                root_dir=self.root_dir,
                working_dir=working_dir, 
                tasks=self.tasks,
                model=model, 
                default_timeout_seconds=self.config.default_timeout_seconds,
                property_kind=self.config.property_kind,
                baseline_timing=self.baseline_timing,
            )
            evaluator = InvBenchEvaluator(config=inv_bench_evaluator_config)
            print(f"Evaluating {model_path_or_name} with {len(self.tasks)} tasks")
            evaluator.evaluate()
            self.model_result_files.append(evaluator.final_results_file_path)
            print(f"Results saved to:\n\t {evaluator.final_results_file_path.relative_to(self.root_dir)}")
            
    def get_metrics(self) -> None:
        print("\n" + "="*80)
        for model_result_file in self.model_result_files:
            model_results = load_json(model_result_file)
            model_name = model_results.get("model_path_or_name", "unknown_model").split("/")[-1]
            self.inv_bench_metrics_without_gen_time.add_model_with_timing_comparison(model_name=model_name, 
                                                                    model_results=model_results, 
                                                                    baseline_timing=self.baseline_timing, 
                                                                    include_model_generation_time=False)
            self.inv_bench_metrics_with_gen_time.add_model_with_timing_comparison(model_name=model_name, 
                                                                    model_results=model_results, 
                                                                    baseline_timing=self.baseline_timing, 
                                                                    include_model_generation_time=True)
        print("\n" + "="*80)

        metrics_path_without_gen_time = self.experiments_dir  /f"metrics_exp_{self.config.exp_id}_without_gen_time.csv"
        metrics_path_with_gen_time = self.experiments_dir /f"metrics_exp_{self.config.exp_id}_with_gen_time.csv"
        
        print("Final Metrics Table without model generation time:")
        self.inv_bench_metrics_without_gen_time.print_table()
        print("\n" + "="*80)
        print("Final Metrics Table with model generation time:")
        self.inv_bench_metrics_with_gen_time.print_table()
        
        self.inv_bench_metrics_without_gen_time.save_results_to_csv(metrics_path_without_gen_time)
        self.inv_bench_metrics_with_gen_time.save_results_to_csv(metrics_path_with_gen_time)
        print(f"Metrics saved to:\n\t {metrics_path_without_gen_time.relative_to(self.root_dir)}")
        print(f"Metrics saved to:\n\t {metrics_path_with_gen_time.relative_to(self.root_dir)}")
        print("\n" + "="*80)
            
def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate a list of models on a InvBench dataset")
    parser.add_argument("--exp_id", type=str, required=True, help="Experiment ID")
    parser.add_argument("--data_split", type=str, required=True, choices=["easy", "hard", "single", "unknowns", "full"], help="Data split")
    parser.add_argument("--models", type=str, required=True, help="Models (space-separated list)")
    parser.add_argument("--limit", type=int, default=-1, help="Limit number of tasks to evaluate (default: -1 for all)")
    parser.add_argument("--default_timeout_seconds", type=int, default=600, help="Default timeout seconds for verification (default: 600)")
    parser.add_argument("--property_kind", type=str, default="unreach", help="Property kind (default: unreach)")
    parser.add_argument("--root_dir", type=str, default="/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv", help="Root directory (default: /cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv)")
    parser.add_argument("--prefix", type=str, default="", help="Prefix for dataset files (default: None)")
    parser.add_argument("--suffix", type=str, default="", help="Suffix for dataset files (default: None)")
    parser.add_argument("--uautomizer_version", type=str, default="uautomizer23", choices=["uautomizer23", "uautomizer24", "uautomizer25", "uautomizer26"], help="UAutomizer version (default: uautomizer23)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    models = args.models.split(" ")
    # args.data_split = "easy"
    config = ExperimentConfig(
        exp_id=args.exp_id,
        root_dir=Path(args.root_dir),
        data_split=args.data_split,
        models=models,
        limit=int(args.limit),
        default_timeout_seconds=args.default_timeout_seconds,
        property_kind=args.property_kind,
        prefix=args.prefix,
        suffix=args.suffix,
        uautomizer_version=args.uautomizer_version
    )
    print("\n" + "="*80)
    print("\nConfig:")
    print(f"  exp_id: {config.exp_id}")
    print(f"  root_dir: {config.root_dir}")
    print(f"  data_split: {config.data_split}")
    print(f"  models: {config.models}")
    print(f"  limit: {config.limit}")
    print(f"  default_timeout_seconds: {config.default_timeout_seconds}")
    print(f"  property_kind: {config.property_kind}")
    print(f"  prefix: {config.prefix}")
    print(f"  suffix: {config.suffix}")
    print(f"  uautomizer_version: {config.uautomizer_version}")
    print("\n" + "="*80)
    experiment = EvalExperiment(config)
    experiment.run()
    experiment.get_metrics()