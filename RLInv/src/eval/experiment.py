from typing import List, Dict
import json
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass, field
from src.eval.evaluate import InvBenchEvaluator
from src.utils.utils import load_dataset, load_baseline_results
from src.eval.model import Model
from src.eval.evaluate import InvBenchEvaluatorConfig
import argparse
from src.eval.metrics import InvBenchMetrics
@dataclass
class Config:
    root_dir: Path = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv")
    uautomizer_path: Path = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/tools/uautomizer/Ultimate.py")
    exp_id: str = "exp_1"
    data_split: str = "easy"
    models: List[str] = field(default_factory=lambda: ["gpt-oss-20b"])
    limit: int = -1
    include_model_generation_time: bool = False
    default_timeout_seconds: int = 600
    property_kind: str = "unreach"

def _sanitize(name: str) -> str:
    return name.replace("/", "_").replace(" ", "_")

# def find_model_result_files(results_dir: Path, pattern: str = "final_results_*.json") -> List[Path]:
#     """Find all model result files matching the pattern."""
#     return sorted(results_dir.glob(pattern))
def load_results(file_path: Path) -> List[Dict]:
    """Load results from JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)
    
class EvalExperiment:
    def __init__(self,config: Config):
        self.config = config 
        self.setup()
        
    def setup(self):
        self.experiments_dir = self.config.root_dir / "experiments" / f"exp_{self.config.exp_id}"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_file = self.config.root_dir / "dataset" / "evaluation" / self.config.data_split / "baseline_results.json"
        self.baseline_results = self.get_baseline_results()
        self.tasks = load_dataset(self.config.root_dir / "dataset" / "evaluation" / self.config.data_split / "yml", property_kind=self.config.property_kind, limit=self.config.limit)
        self.metrics_path = self.experiments_dir / f"metrics_exp_{self.config.exp_id}.csv"
        self.inv_bench_metrics = InvBenchMetrics()
        self.model_result_files = []
    
    def get_baseline_results(self):
        baseline_results = load_baseline_results(self.baseline_file)
        if baseline_results is None or len(baseline_results) == 0:
            # Run baseline script via subprocess
            eval_dir = self.config.root_dir / "dataset" / "evaluation" / self.config.data_split
            baseline_script = self.config.root_dir / "src" / "eval" / "baseline.py"
            print(f"Baseline results not found. Running baseline evaluation for {self.config.data_split} split...")
            subprocess.run([
                sys.executable, 
                str(baseline_script),
                str(eval_dir),
                "--timeout", str(self.config.default_timeout_seconds),
                "--uautomizer-path", str(self.config.uautomizer_path)
            ], check=True)
            baseline_results = load_baseline_results(self.baseline_file)
            print(f"Baseline evaluation completed. Loaded {len(baseline_results)} baseline results.")
        return baseline_results
            
    def run(self):
        self.get_baseline_results()
        for model_path_or_name in self.config.models:
            working_dir = self.experiments_dir / f"{_sanitize(model_path_or_name)}"
            model = Model(model_path_or_name=model_path_or_name)
            inv_bench_evaluator_config = InvBenchEvaluatorConfig(
                working_dir=working_dir, 
                tasks=self.tasks,
                model=model, 
                baseline_results=self.baseline_results,
                default_timeout_seconds=self.config.default_timeout_seconds,
                uautomizer_executable_path=self.config.uautomizer_path,
                property_kind=self.config.property_kind
            )
            evaluator = InvBenchEvaluator(config=inv_bench_evaluator_config)
            print(f"Evaluating {model_path_or_name} with {len(self.tasks)} tasks")
            evaluator.evaluate()  # Results are saved to final_results_file_path
            # Store the path to the saved results file
            self.model_result_files.append(evaluator.final_results_file_path)
            print(f"Results saved to:\n\t {evaluator.final_results_file_path.relative_to(self.experiments_dir)}")
    def get_metrics(self) -> None:
        print("\n" + "="*80)
        print(f"Calculating metrics for {len(self.model_result_files)} models")
        # model_result_files = find_model_result_files(self.experiments_dir)
        for model_result_file in self.model_result_files:
            model_results = load_results(model_result_file)
            model_name = model_results.get("model_path_or_name", "unknown_model")
            self.inv_bench_metrics.add_model_with_timing_comparison(model_name=model_name, 
                                                                    model_results=model_results, 
                                                                    baseline_results=self.baseline_results, 
                                                                    include_model_generation_time=self.config.include_model_generation_time)
        print("\n" + "="*80)
        print("Final Metrics Table:")
        self.inv_bench_metrics.print_table()
        self.inv_bench_metrics.save_results_to_csv(self.metrics_path)
        print(f"Metrics saved to:\n\t {self.metrics_path.relative_to(self.experiments_dir)}")
        print("\n" + "="*80)
            
def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate a list of models on a InvBench dataset")
    parser.add_argument("--exp_id", type=str, required=True, help="Experiment ID")
    parser.add_argument("--data_split", type=str, required=True, choices=["easy", "hard"], help="Data split")
    parser.add_argument("--models", type=str, required=True, help="Models (space-separated list)")
    parser.add_argument("--limit", type=int, default=-1, help="Limit number of tasks to evaluate (default: -1 for all)")
    parser.add_argument("--include_model_generation_time", action="store_true", help="Include model generation time in speedup calculations (default: False, uses verification time only)")
    parser.add_argument("--default_timeout_seconds", type=int, default=600, help="Default timeout seconds for verification (default: 600)")
    parser.add_argument("--property_kind", type=str, default="unreach", help="Property kind (default: unreach)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    models = args.models.split(" ")
    config = Config(exp_id=args.exp_id,
                    data_split=args.data_split,
                    models=models,
                    limit=args.limit,
                    include_model_generation_time=args.include_model_generation_time,
                    default_timeout_seconds=args.default_timeout_seconds,
                    property_kind=args.property_kind)
    print("\n" + "="*80)
    print(f"\nConfig:")
    print(f"  exp_id: {config.exp_id}")
    print(f"  data_split: {config.data_split}")
    print(f"  models: {config.models}")
    print(f"  limit: {config.limit}")
    print(f"  include_model_generation_time: {config.include_model_generation_time}")
    print(f"  default_timeout_seconds: {config.default_timeout_seconds}")
    print(f"  property_kind: {config.property_kind}")
    print("\n" + "="*80)
    experiment = EvalExperiment(config)
    experiment.run()
    experiment.get_metrics()