import time
import re
import argparse
from pathlib import Path
from shutil import copy
from typing import List, Optional, Dict
from tqdm import tqdm
from dataclasses import dataclass
import os
from src.eval.model import Model, ModelConfig
from src.utils.task import Task
from src.utils.rewriter import Rewriter
from src.utils.program import Program
from src.eval.decision_procedure import DecisionProcedure
from src.utils.utils import save_as_json, load_json
from src.eval.metrics import InvBenchMetrics
from src.utils.paths import EVALUATION_DATASET_DIR, EXPERIMENTS_DIR, UAUTOMIZER_PATHS
import weave

def load_tasks(
    dataset_path: Path,
    baseline: Dict,
    property_kind: str = "unreach",
    limit: int = None,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
    data_split: str = "easy"

) -> List[Task]:
    """Load dataset from YAML files. Filter tasks based on baseline data split."""
    tasks = []
    baseline_lookup = {r["file"]: r["split"] for r in baseline}
    print(f"Loading dataset from: {dataset_path}")
    print(f"Loading {limit} {data_split} tasks")
    for yml_file in dataset_path.glob("*.yml"):
        file_name = yml_file.stem
        c_filename = file_name + ".c"
        if c_filename not in baseline_lookup:
            continue
        # c_file_path = dataset_path / base_filename
        if baseline_lookup[c_filename] != data_split:
            continue
        if limit is not None and limit != -1 and len(tasks) >= limit:
            break
        if prefix is not None and not yml_file.stem.startswith(prefix):
            continue
        if suffix is not None and not yml_file.stem.endswith(suffix):
            continue
        task = Task(directory=dataset_path, filename=file_name, property_kind=property_kind)
        tasks.append(task)
    print(tasks[0])
    return tasks

def setup_weave_exp(project_name: str):
    weave.init(f'ip-ai/{project_name}')

@dataclass
class InvBenchEvaluatorConfig:
    """Unified configuration for evaluation experiments."""
    # Experiment identification
    project_name: str = "rlinv"
    exp_id: str = "exp_1"
    
    # Dataset configuration
    baseline_dir: str = "uautomizer25_evaluation_k3_rewrite"
    data_split: str = "easy"  # "easy", "hard", "all"
    property_kind: str = "unreach"
    limit: int = -1
    prefix: Optional[str] = None
    suffix: Optional[str] = None    
    # Evaluation configuration
    default_timeout_seconds: float = 600.0
    compute_metrics: bool = False
    # results_filename: str = "model_results.json"

class InvBenchEvaluator:
    """
        A class for evaluating invariant synthesis models on the InvBench evaluation benchmark.

        This class manages experiment setup, including loading datasets, configuring tasks, initializing model evaluators, 
        tracking metrics, and storing evaluation results.

        Usage:
            1. Initialize with an InvBenchEvaluatorConfig and a list of ModelConfig instances.
            2. The class sets up the experiment environment, loads the baseline data and tasks.
            3. Evaluators can be created for models and results can be computed and analyzed.

        Attributes:
            config (InvBenchEvaluatorConfig): Configuration for the experiment and dataset.
            model_configs (List[ModelConfig]): List of model configuration objects.
            tasks (List[Task]): List of loaded evaluation tasks.
            inv_bench_metrics_without_gen_time (InvBenchMetrics): Metrics tracker excluding generation time.
            inv_bench_metrics_with_gen_time (InvBenchMetrics): Metrics tracker including generation time.
            model_result_files (List): Paths to model result files created during evaluation.
            baseline_timing_lookup (dict): Maps each task to its baseline timing information.

        Methods:
            setup():
                Initializes paths, loads baseline and tasks, and sets up metrics tracking.

            create_evaluators_for_model(model: Model, working_dir: Path) -> List[Dict]:
                Creates evaluator components for all tasks for a given model.

            evaluate_model(model: Model, working_dir: Path) -> dict:
                Evaluates a single model on all tasks.

            get_metrics() -> None:
                Computes and saves metrics for all evaluated models.

            run() -> None:
                Runs evaluation for all configured models.
    """
    
    def __init__(self, config: InvBenchEvaluatorConfig, model_configs: List[ModelConfig]):
        self.config = config
        self.model_configs = model_configs
        self.setup()
        
    def setup(self):
        """Initialize paths, load baseline, and prepare tasks."""
        # Derive UAutomizer version and path
        self.uautomizer_version = self.config.baseline_dir.split("_")[0].replace("uautomizer", "")
        self.uautomizer_path = UAUTOMIZER_PATHS[self.uautomizer_version]
        # print(f"UAutomizer path: {self.uautomizer_path}")
        # Create experiment directory
        EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
        self.baseline_file_path = EVALUATION_DATASET_DIR / self.config.baseline_dir / f"{self.config.baseline_dir}.json"
        self.dataset_path = EVALUATION_DATASET_DIR / "orig_programs"
        # Load baseline data
        self.baseline = load_json(file_path=self.baseline_file_path)
        if len(self.baseline) == 0:
            raise ValueError(f"Evaluation JSON file {self.baseline_file_path} is empty")
    
        # Load tasks based on baseline split
        self.tasks = load_tasks(
            dataset_path=self.dataset_path,
            baseline=self.baseline,
            property_kind=self.config.property_kind,
            limit=self.config.limit,
            prefix=self.config.prefix,
            suffix=self.config.suffix,
            data_split=self.config.data_split,
        )
        # Initialize metrics trackers
        self.inv_bench_metrics_without_gen_time = InvBenchMetrics()
        self.inv_bench_metrics_with_gen_time = InvBenchMetrics()
        self.model_result_files = []
        
        # Baseline timing lookup
        self.baseline_timing_lookup = {Path(r["file"]).stem: r["timings"]["median"] for r in self.baseline}

    def create_evaluators_for_model(self, model: Model, working_dir: Path) -> List[Dict]:
        """Create evaluator components for all tasks for a given model."""
        evaluators = []
        
        for i, task in tqdm(enumerate(self.tasks), total=len(self.tasks), desc="Creating evaluators"):
            task_dir = working_dir / f"task_{i}_{task.source_code_path.stem}"
            task_dir.mkdir(parents=True, exist_ok=True)
            code_dir = task_dir / "code"
            code_dir.mkdir(parents=True, exist_ok=True)
            c_program_path = code_dir / "base.c"
            target_property_path = code_dir / "property"
            copy(task.source_code_path, c_program_path)
            copy(task.property_path, target_property_path)
            r = Rewriter(c_program_path, rewrite=True)
            program = Program(r.lines_to_verify, r.replacement)
            
            # Determine timeout
            task_base_filename = task.yml_file.stem
            baseline_time = self.baseline_timing_lookup.get(task_base_filename, 0.0)
            timeout_seconds = baseline_time if baseline_time > 0 else self.config.default_timeout_seconds
            
            # Create decision procedure
            decision_procedure = DecisionProcedure(
                program=program,
                target_property_file_path=target_property_path,
                arch=task.arch,
                code_dir=code_dir,
                uautomizer_path=self.uautomizer_path,
                timeout_seconds=timeout_seconds,
            )
            evaluators.append({
                'task': task,
                'working_dir': task_dir,
                'code_dir': code_dir,
                'program': program,
                'decision_procedure': decision_procedure,
                'baseline_time': baseline_time,
            })
        
        return evaluators
    
    def evaluate_model(self, model: Model, working_dir: Path) -> dict:
        """Evaluate a single model on all tasks."""
        evaluators = self.create_evaluators_for_model(model, working_dir)
        final_results = {
            'evaluation_timestamp': time.strftime('%Y%m%d_%H%M%S'),
            'model_path_or_name': model.model_config.model_path_or_name,
            'total_tasks': len(evaluators),
            'results': []
        }
        
        for i, evaluator_data in tqdm(enumerate(evaluators), total=len(evaluators), desc="Evaluating tasks"):
            task = evaluator_data['task']
            program = evaluator_data['program']
            decision_procedure = evaluator_data['decision_procedure']
            print(f"\n--- Evaluating task {i+1}/{len(evaluators)}: {task.source_code_path.name} ---")
            
            # Generate candidate invariant
            model_gen_start = time.perf_counter()
            candidate_invariant = model.generate_candidate_invariant(program=program)
            model_gen_time = time.perf_counter() - model_gen_start
            
            # Run decision procedure
            baseline_time = self.baseline_timing_lookup.get(task.yml_file.stem, 0.0)
            report = decision_procedure.run(candidate_invariant, model_gen_time)
            
            if report.syntactic_validation_result:
                report.total_time_taken = report.verification_time_taken + model_gen_time
                correctness_info = "N/A (short-circuited)" if report.invariant_correctness_report is None else f"{report.invariant_correctness_report.decision} - {report.invariant_correctness_report.time_taken:.2f}s"
                print(f"""Decision Procedure summary: 
                    '\t Target assert: {decision_procedure.target_assert}
                    '\t Candidate invariant: {candidate_invariant}
                    '\t valid invariant: {report.syntactic_validation_result}
                    '\t final decision: {report.final_decision}
                    '\t Decision rule: {report.decision_rule}
                    '\t Decision Procedure Timeout (equals to UAutomizer median time on that task): {baseline_time:.2f}s
                    '\t Model generation time: {model_gen_time:.2f}s
                    '\t Correctness: {correctness_info}
                    '\t Usefulness: {report.invariant_usefulness_report.decision} - {report.invariant_usefulness_report.time_taken:.2f}s
                    '\t Verification time (max(correctness, usefulness)): {report.verification_time_taken:.2f}s
                    '\t Total time (verification + model generation): {report.total_time_taken:.2f}s
                """)
            else:
                print(f"""Decision Procedure summary: 
                    '\t Target assert: {decision_procedure.target_assert}
                    '\t Candidate invariant: {candidate_invariant}
                    '\t valid invariant: {report.syntactic_validation_result}
                    '\t final decision: {report.final_decision}
                """)
            
            task_result = {
                'task_index': i,
                'task_name': task.yml_file.stem,
                'task_path': str(task.source_code_path),
                'property_path': str(task.property_path),
                'uautomizer_path': str(self.uautomizer_path),
                'arch': task.arch,
                "baseline_time": baseline_time,
                'report': report.to_dict()
            }
            
            final_results['results'].append(task_result)
        
        return final_results
    

    
    def get_metrics(self) -> None:
        """Compute and save metrics for all evaluated models."""
        print("\n" + "="*80)
        for model_result_file in self.model_result_files:
            model_results = load_json(model_result_file)
            model_name = model_results.get("model_path_or_name", "unknown_model").split("/")[-1]
            print(f"Model name: {model_name}")
            self.inv_bench_metrics_without_gen_time.add_model_with_timing_comparison(
                model_name=model_name,
                model_results=model_results,
                baseline=self.baseline,
                include_model_generation_time=False
            )
            self.inv_bench_metrics_with_gen_time.add_model_with_timing_comparison(
                model_name=model_name,
                model_results=model_results,
                baseline=self.baseline,
                include_model_generation_time=True
            )
        
        print("\n" + "="*80)
        metrics_dir = EXPERIMENTS_DIR / self.config.exp_id / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        
        metrics_path_without_gen_time = metrics_dir / f"metrics_exp_{self.config.exp_id}_without_gen_time.csv"
        metrics_path_with_gen_time = metrics_dir / f"metrics_exp_{self.config.exp_id}_with_gen_time.csv"
        
        print("Final Metrics Table without model generation time:")
        self.inv_bench_metrics_without_gen_time.print_table()
        print("\n" + "="*80)
        print("Final Metrics Table with model generation time:")
        self.inv_bench_metrics_with_gen_time.print_table()
        
        self.inv_bench_metrics_without_gen_time.save_results_to_csv(metrics_path_without_gen_time)
        self.inv_bench_metrics_with_gen_time.save_results_to_csv(metrics_path_with_gen_time)
        print("\n" + "="*80)

    def run(self):
        """Run evaluation for all configured models."""
        for model_config in self.model_configs:
            model = Model(model_config=model_config)
            working_dir = EXPERIMENTS_DIR / self.config.exp_id / f"{model.model_config.nickname}"
            working_dir.mkdir(parents=True, exist_ok=True)
            final_results = self.evaluate_model(model, working_dir)
            results_filename = f"{model.model_config.nickname}_results.json"
            final_results_file_path = working_dir / results_filename
            save_as_json(final_results, final_results_file_path)
            self.model_result_files.append(str(final_results_file_path))
            if self.config.compute_metrics:
                self.get_metrics()
            print(f"Evaluation results saved to {str(final_results_file_path)}")

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Evaluate models on InvBench dataset")
    parser.add_argument("--project_name", type=str,default="rlinv", required=False, help="Project name")
    parser.add_argument("--exp_id", type=str, required=True, help="Experiment ID")
    parser.add_argument("--baseline_dir", type=str, default="uautomizer25_evaluation_k3_rewrite", 
                       help="Baseline directory")
    parser.add_argument("--property_kind", type=str, default="unreach", 
                       help="Property kind (default: unreach)")
    parser.add_argument("--data_split", type=str, required=True, choices=["easy", "hard"], 
                       help="Data split")
    parser.add_argument("--default_timeout_seconds", type=float, default=600.0, 
                       help="Default timeout seconds (default: 600.0)")

    parser.add_argument("--compute_metrics", action="store_true", 
                       help="Compute and save metrics after evaluation")

    # Dataset configuration
    parser.add_argument("--limit", type=int, default=-1, 
                       help="Limit number of tasks (default: -1 for all)")
    parser.add_argument("--prefix", type=str, default="", 
                       help="Prefix for dataset files (default: None)")
    parser.add_argument("--suffix", type=str, default="", 
                       help="Suffix for dataset files (default: None)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    models = [
        {
            "client": "together",
            "model_path_or_name": "openai/gpt-oss-20b",
            "nickname": "gpt-oss-20b",
            "sampling_params": {
                "temperature": 0.0,
                "max_tokens": 2048,
                "reasoning_effort": "low",
                "n": 1,
            }
        }
    ]
    models_configs = [ModelConfig.from_dict(model) for model in models]
    evaluator_config = InvBenchEvaluatorConfig(
        project_name=args.project_name,
        exp_id=args.exp_id,
        baseline_dir=args.baseline_dir,
        data_split=args.data_split,
        limit=int(args.limit),
        default_timeout_seconds=args.default_timeout_seconds,
        property_kind=args.property_kind,
        prefix=args.prefix if args.prefix else None,
        suffix=args.suffix if args.suffix else None,
        compute_metrics=args.compute_metrics,
    )
    evaluator = InvBenchEvaluator(config=evaluator_config, model_configs=models_configs)
    evaluator.run()

    