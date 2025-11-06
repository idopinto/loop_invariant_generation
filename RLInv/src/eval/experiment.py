from typing import List, Optional
import subprocess
import sys
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
    include_model_generation_time: bool = False
    default_timeout_seconds: int = 600
    property_kind: str = "unreach"
    prefix: Optional[str] = None
    suffix: Optional[str] = None


class EvalExperiment:
    def __init__(self,config: ExperimentConfig):
        self.config = config 
        self.root_dir = self.config.root_dir
        self.setup()
        
    def setup(self):
        self.uautomizer_executable_path = self.root_dir / "tools" / "uautomizer" / "Ultimate.py"
        self.experiments_dir = self.root_dir / "experiments" / f"exp_{self.config.exp_id}"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_file = self.root_dir / "dataset" / "evaluation" / self.config.data_split / "baseline_timing.json"
        self.baseline_timing = self.get_baseline_timing()
        self.tasks = load_dataset(dataset_path=self.root_dir / "dataset" / "evaluation" / self.config.data_split / "yml", 
                                  property_kind=self.config.property_kind, 
                                  limit=self.config.limit,
                                  prefix=self.config.prefix,
                                  suffix=self.config.suffix)
        self.metrics_path = self.experiments_dir / f"metrics_exp_{self.config.exp_id}.csv"
        self.inv_bench_metrics = InvBenchMetrics()
        self.model_result_files = []
    
    def get_baseline_timing(self):
        baseline_timing = load_json(file_path=self.baseline_file)
        if baseline_timing is None or len(baseline_timing) == 0:
            # Run baseline script via subprocess
            eval_dir = self.root_dir / "dataset" / "evaluation" / self.config.data_split
            baseline_script = self.root_dir / "src" / "eval" / "baseline.py"
            print(f"Baseline results not found. Running baseline evaluation for {self.config.data_split} split...")
            response = input("Baseline results not found. Run baseline evaluation? (y/n): ")
            if response == "y":
                subprocess.run([
                    sys.executable, 
                    str(baseline_script),
                    str(eval_dir),
                    "--timeout", str(self.config.default_timeout_seconds),
                    "--uautomizer-path", str(self.uautomizer_executable_path)
                ], check=True)
                baseline_timing = load_json(file_path=self.baseline_file)
                print(f"Baseline evaluation completed. Loaded {len(baseline_timing)} baseline timing.")
            else:
                print("Baseline evaluation not run. Exiting...")
                sys.exit(1)
        else:
            print(f"Baseline results found in {self.baseline_file}")
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
        print(f"Calculating metrics for {len(self.model_result_files)} models")
        # model_result_files = find_model_result_files(self.experiments_dir)
        for model_result_file in self.model_result_files:
            model_results = load_json(model_result_file)
            model_name = model_results.get("model_path_or_name", "unknown_model")
            self.inv_bench_metrics.add_model_with_timing_comparison(model_name=model_name, 
                                                                    model_results=model_results, 
                                                                    baseline_timing=self.baseline_timing, 
                                                                    include_model_generation_time=self.config.include_model_generation_time)
        print("\n" + "="*80)
        print("Final Metrics Table:")
        self.inv_bench_metrics.print_table()
        self.inv_bench_metrics.save_results_to_csv(self.metrics_path)
        print(f"Metrics saved to:\n\t {self.metrics_path.relative_to(self.root_dir)}")
        print("\n" + "="*80)
            
def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate a list of models on a InvBench dataset")
    parser.add_argument("--exp_id", type=str, required=True, help="Experiment ID")
    parser.add_argument("--data_split", type=str, required=True, choices=["easy", "hard", "single", "unknowns", "full"], help="Data split")
    parser.add_argument("--models", type=str, required=True, help="Models (space-separated list)")
    parser.add_argument("--limit", type=int, default=-1, help="Limit number of tasks to evaluate (default: -1 for all)")
    parser.add_argument("--include_model_generation_time", action="store_true", help="Include model generation time in speedup calculations (default: False, uses verification time only)")
    parser.add_argument("--default_timeout_seconds", type=int, default=600, help="Default timeout seconds for verification (default: 600)")
    parser.add_argument("--property_kind", type=str, default="unreach", help="Property kind (default: unreach)")
    parser.add_argument("--root_dir", type=str, default="/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv", help="Root directory (default: /cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv)")
    parser.add_argument("--prefix", type=str, default="interleave_bits", help="Prefix for dataset files (default: None)")
    parser.add_argument("--suffix", type=str, default="", help="Suffix for dataset files (default: None)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    models = args.models.split(" ")
    args.data_split = "easy"
    args.include_model_generation_time = True
    config = ExperimentConfig(
        exp_id=args.exp_id,
        root_dir=Path(args.root_dir),
        data_split=args.data_split,
        models=models,
        limit=args.limit,
        include_model_generation_time=args.include_model_generation_time,
        default_timeout_seconds=args.default_timeout_seconds,
        property_kind=args.property_kind,
        prefix=args.prefix,
        suffix=args.suffix
    )
    print("\n" + "="*80)
    print(f"\nConfig:")
    print(f"  exp_id: {config.exp_id}")
    print(f"  root_dir: {config.root_dir}")
    print(f"  data_split: {config.data_split}")
    print(f"  models: {config.models}")
    print(f"  limit: {config.limit}")
    print(f"  include_model_generation_time: {config.include_model_generation_time}")
    print(f"  default_timeout_seconds: {config.default_timeout_seconds}")
    print(f"  property_kind: {config.property_kind}")
    print(f"  prefix: {config.prefix}")
    print(f"  suffix: {config.suffix}")
    print("\n" + "="*80)
    experiment = EvalExperiment(config)
    experiment.run()
    experiment.get_metrics()