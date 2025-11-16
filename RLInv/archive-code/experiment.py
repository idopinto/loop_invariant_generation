from typing import List, Optional, Dict
from dataclasses import dataclass, field
from src.eval.evaluate import InvBenchEvaluator
# from src.utils.utils import load_dataset
from src.eval.model import Model
from src.eval.evaluate import InvBenchEvaluatorConfig
import argparse
from src.eval.metrics import InvBenchMetrics
from src.utils.utils import load_json
from src.utils.paths import EVALUATION_DATASET_DIR, EXPERIMENTS_DIR, UAUTOMIZER_PATHS
import re
from pathlib import Path
from src.utils.task import Task

def _sanitize(name: str) -> str:
    """Sanitize a model name/path for use as a directory name."""
    # Replace path separators and other problematic characters with underscores
    sanitized = re.sub(r'[^\w\-_.]', '_', name)
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized

def load_tasks(dataset_path: Path,baseline: Dict, property_kind: str = "unreach", limit: int = None, prefix: Optional[str] = None, suffix: Optional[str] = None, data_split: str = "easy") -> List[Task]:
    """Load dataset from YAML files. Filter tasks based on baseline data split."""
    tasks = []
    baseline_lookup = {r["file"]: r["split"] for r in baseline}
    print(f"Loading dataset from: {dataset_path}")
    print(f"Loading {limit} {data_split} tasks")
    # print(f"Baseline lookup: {baseline_lookup}")
    for yml_file in dataset_path.glob("*.yml"):
        base_filename = yml_file.stem + ".c"
        # print(f"Base filename: {base_filename}")
        if base_filename not in baseline_lookup:
            # print(f"Skipping {base_filename} because it is not in baseline")
            continue
        if baseline_lookup[base_filename] != data_split:
            # print(f"Skipping {base_filename} because it is not in {data_split} split")
            continue
        if limit is not None and limit != -1 and len(tasks) >= limit:
            break
        if prefix is not None and not yml_file.stem.startswith(prefix):
            continue
        if suffix is not None and not yml_file.stem.endswith(suffix):
            continue
        task = Task(yml_file_path=yml_file, property_kind=property_kind)
        tasks.append(task)
    return tasks    



@dataclass
class ExperimentConfig:
    exp_id: str = "exp_1"
    baseline_dir: str = "uautomizer25_evaluation_k3_rewrite"
    data_split: str = "easy" # "easy", "hard", "all"
    models: List[str] = field(default_factory=lambda: ["gpt-oss-20b"])
    limit: int = -1
    default_timeout_seconds: float = 600.0
    property_kind: str = "unreach"
    prefix: Optional[str] = None
    suffix: Optional[str] = None


class EvalExperiment:
    def __init__(self,config: ExperimentConfig):
        self.config = config 
        self.setup()
        
    def setup(self):
        self.uautomizer_version = self.config.baseline_dir.split("_")[0].replace("uautomizer", "") # assume this format: uautomizerXX_evaluation_kX_rewrite
        self.uautomizer_path = UAUTOMIZER_PATHS[self.uautomizer_version]


        self.orig_programs_dir = EVALUATION_DATASET_DIR / "orig_programs"
        self.baseline_file =  EVALUATION_DATASET_DIR / self.config.baseline_dir / f"{self.config.baseline_dir}.json"

        self.experiment_dir = EXPERIMENTS_DIR / self.config.exp_id
        self.experiment_dir.mkdir(parents=True, exist_ok=True)

        self.baseline = load_json(file_path=self.baseline_file)
        if len(self.baseline) == 0:
            raise ValueError(f"Evaluation JSON file {self.baseline_file} is empty")
        # print(f"Baseline has {len(self.baseline)} tasks")
        self.tasks = load_tasks(dataset_path=self.orig_programs_dir, 
                                  baseline=self.baseline,
                                  property_kind=self.config.property_kind, 
                                  limit=self.config.limit,
                                  prefix=self.config.prefix,
                                  suffix=self.config.suffix,
                                  data_split=self.config.data_split,)
        # print(f"Loaded {len(self.tasks)} tasks")
        self.inv_bench_metrics_without_gen_time = InvBenchMetrics()
        self.inv_bench_metrics_with_gen_time = InvBenchMetrics()
        self.model_result_files = []
    
    def run(self):
        for model_path_or_name in self.config.models:
            working_dir = self.experiment_dir / f"{_sanitize(model_path_or_name)}"
            print(f"Running {model_path_or_name} with {len(self.tasks)} tasks")
            model = Model(model_path_or_name=model_path_or_name)
            inv_bench_evaluator_config = InvBenchEvaluatorConfig(
                working_dir=working_dir, 
                tasks=self.tasks,
                model=model, 
                default_timeout_seconds=self.config.default_timeout_seconds,
                property_kind=self.config.property_kind,
                baseline_timing_file=str(self.baseline_file),
            )
            evaluator = InvBenchEvaluator(config=inv_bench_evaluator_config)
            print(f"Evaluating {model_path_or_name} with {len(self.tasks)} tasks")
            evaluator.evaluate()
            self.model_result_files.append(evaluator.final_results_file_path)
            
    def get_metrics(self) -> None:
        print("\n" + "="*80)
        for model_result_file in self.model_result_files:
            model_results = load_json(model_result_file)
            model_name = model_results.get("model_path_or_name", "unknown_model").split("/")[-1]
            self.inv_bench_metrics_without_gen_time.add_model_with_timing_comparison(model_name=model_name, 
                                                                    model_results=model_results, 
                                                                    baseline_timing=self.eval_baseline, 
                                                                    include_model_generation_time=False)
            self.inv_bench_metrics_with_gen_time.add_model_with_timing_comparison(model_name=model_name, 
                                                                    model_results=model_results, 
                                                                    baseline_timing=self.eval_baseline, 
                                                                    include_model_generation_time=True)
        print("\n" + "="*80)
        metrics_dir = self.experiment_dir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        metrics_path_without_gen_time = metrics_dir /f"metrics_exp_{self.config.exp_id}_without_gen_time.csv"
        metrics_path_with_gen_time = metrics_dir /f"metrics_exp_{self.config.exp_id}_with_gen_time.csv"
        
        print("Final Metrics Table without model generation time:")
        self.inv_bench_metrics_without_gen_time.print_table()
        print("\n" + "="*80)
        print("Final Metrics Table with model generation time:")
        self.inv_bench_metrics_with_gen_time.print_table()
        
        self.inv_bench_metrics_without_gen_time.save_results_to_csv(metrics_path_without_gen_time)
        self.inv_bench_metrics_with_gen_time.save_results_to_csv(metrics_path_with_gen_time)
        print("\n" + "="*80)
        
def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate a list of models on a InvBench dataset")
    parser.add_argument("--exp_id", type=str, required=True, help="Experiment ID")
    parser.add_argument("--baseline_dir", type=str,default="uautomizer25_evaluation_k3_rewrite", required=True, help="Baseline directory")
    parser.add_argument("--data_split", type=str, required=True, choices=["easy", "hard", "all"], help="Data split")
    parser.add_argument("--models", type=str, required=True, help="Models (space-separated list)")
    parser.add_argument("--limit", type=int, default=-1, help="Limit number of tasks to evaluate (default: -1 for all)")
    parser.add_argument("--default_timeout_seconds", type=float, default=600.0, help="Default timeout seconds for verification (default: 600.0)")
    parser.add_argument("--property_kind", type=str, default="unreach", help="Property kind (default: unreach)")
    parser.add_argument("--prefix", type=str, default="", help="Prefix for dataset files (default: None)")
    parser.add_argument("--suffix", type=str, default="", help="Suffix for dataset files (default: None)")
    # parser.add_argument("--uautomizer_version", type=str, default="25", choices=["23", "24", "25", "26"], help="UAutomizer version (default: 23)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    models = args.models.split(" ")
    config = ExperimentConfig(
        exp_id=args.exp_id,
        baseline_dir=args.baseline_dir,
        data_split=args.data_split,
        models=models,
        limit=int(args.limit),
        default_timeout_seconds=args.default_timeout_seconds,
        property_kind=args.property_kind,
        prefix=args.prefix,
        suffix=args.suffix,
    )
    print("\n" + "="*80)
    print("\nConfig:")
    print(f"  exp_id: {config.exp_id}")
    print(f"  baseline_dir: {config.baseline_dir}")
    print(f"  data_split: {config.data_split}")
    print(f"  models: {config.models}")
    print(f"  limit: {config.limit}")
    print(f"  default_timeout_seconds: {config.default_timeout_seconds}")
    print(f"  property_kind: {config.property_kind}")
    print(f"  prefix: {config.prefix}")
    print(f"  suffix: {config.suffix}")
    print("\n" + "="*80)
    experiment = EvalExperiment(config)

    experiment.run()
    # experiment.get_metrics()