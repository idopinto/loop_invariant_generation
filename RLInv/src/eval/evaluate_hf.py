"""
Evaluation script for HuggingFace models.
Uses the same evaluation procedure as evaluate.py but with local HuggingFace inference.
"""
import time
import argparse
from pathlib import Path
from shutil import copy
from typing import List, Optional, Dict
from tqdm import tqdm
from dataclasses import dataclass, asdict

from src.eval.models.hf_model import HuggingFaceModel
from src.utils.task import Task
from src.utils.rewriter import Rewriter
from src.utils.program import Program
from src.eval.decision_procedure import DecisionProcedure
from src.utils.utils import save_as_json, load_json
from src.eval.metrics import InvBenchMetrics
from src.utils.paths import EVALUATION_DATASET_DIR, EXPERIMENTS_DIR, UAUTOMIZER_PATHS

EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)


def load_tasks(
    dataset_path: Path,
    baseline: Dict,
    property_kind: str = "unreach",
    limit: int = None,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
    data_split: str = "easy"
) -> List[Task]:
    """
       Load dataset from YAML files. 
       Filter tasks based on baseline data split.
       Assumes the YAML files are in the dataset_path directory and the C files are in the same directory with the same name but with .c extension.
    """
    tasks = []
    baseline_lookup = {r["file"]: r["split"] for r in baseline}
    dataset_paths = list(dataset_path.glob("*.yml")) 
    print(f"Loading dataset from: {dataset_path} with {len(dataset_paths)} tasks")
    limit_str = "all" if limit is None or limit == -1 else limit
    print(f"Loading {limit_str} {data_split} tasks with prefix: {prefix} and suffix: {suffix}")
    for yml_file in dataset_paths:
        file_name = yml_file.stem
        c_filename = file_name + ".c"
        if c_filename not in baseline_lookup:
            continue
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
    print(f"Loaded {len(tasks)} {data_split} tasks with prefix: {prefix} and suffix: {suffix}")
    print("="*80)
    print(f"Example task:\n {tasks[0]}")
    print("="*80)
    return tasks


@dataclass
class InvBenchHFEvaluatorConfig:
    """Unified configuration for HuggingFace evaluation experiments."""
    # Experiment identification
    project_name: str = "rlinv-hf"
    exp_id: str = "hf_eval"
    models_configs_path: Optional[str] = None
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
    baseline_is_timeout: bool = False


class InvBenchHFEvaluator:
    """
    A class for evaluating HuggingFace invariant synthesis models on the InvBench evaluation benchmark.
    Uses local HuggingFace inference instead of API calls.
    """
    
    def __init__(self, config: InvBenchHFEvaluatorConfig):
        self.config = config
        self.setup()

    def _save_config(self, working_dir: Path):
        config_dict = asdict(self.config)
        config_dict["full_exp_id"] = self.full_exp_id
        config_dict["models_configs"] = self.model_configs 
        save_as_json(config_dict, working_dir / f"{self.full_exp_id}_config.json")
        print("="*80)
        print("Config:")
        for key, value in config_dict.items():
            if isinstance(value, list):
                for item in value:
                    print(f"\t\t{item}")
            else:
                print(f"\t{key}: {value}")
        print("="*80)
        print(f"Config saved to {working_dir / f'{self.full_exp_id}_config.json'}")
        print("="*80)

    def setup(self):
        """Initialize paths, load baseline, and prepare tasks."""
        limit_str = "all" if self.config.limit is None or self.config.limit == -1 else str(self.config.limit)
        baseline_timeout_str = "bs_timeout" if self.config.baseline_is_timeout else "no_bs_timeout"
        self.full_exp_id = self.config.exp_id + "_" + self.config.data_split + "_" + limit_str + "_" + baseline_timeout_str
        self.exp_dir = EXPERIMENTS_DIR / self.full_exp_id
        self.exp_dir.mkdir(parents=True, exist_ok=True)
        self.model_configs = load_json(file_path=Path(self.config.models_configs_path))
        self._save_config(working_dir=self.exp_dir)
        # Derive UAutomizer version and path
        self.baseline_name = self.config.baseline_dir.split("_")[0]
        self.uautomizer_version = self.baseline_name.replace("uautomizer", "")
        self.uautomizer_path = UAUTOMIZER_PATHS[self.uautomizer_version]
        # Create experiment directory
        self.baseline_file_path = EVALUATION_DATASET_DIR / self.config.baseline_dir / f"{self.config.baseline_dir}.json"
        # Load baseline data
        self.baseline = load_json(file_path=self.baseline_file_path)
    
        # Baseline timing lookup
        self.baseline_timing_lookup = {Path(r["file"]).stem: r["timings"]["median"] for r in self.baseline}
    
        self.dataset_path = EVALUATION_DATASET_DIR / "orig_programs"
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
        self.model_result_files = []
        self.all_metrics = []

    def create_evaluators(self, working_dir: Path) -> List[Dict]:
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
            # Set the timeout to baseline time
            if self.config.baseline_is_timeout:
                timeout_seconds = baseline_time if baseline_time > 0 else self.config.default_timeout_seconds
            else:
                timeout_seconds = self.config.default_timeout_seconds
            
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
                'task_dir': task_dir,
            })
        
        return evaluators
    
    def evaluate_model(self, model: HuggingFaceModel, working_dir: Path) -> dict:
        """Evaluate a single HuggingFace model on all tasks."""
        evaluators = self.create_evaluators(working_dir)
        final_results = {
            'evaluation_timestamp': time.strftime('%Y%m%d_%H%M%S'),
            'model_path_or_name': model.model_config["model_path_or_name"],
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
            candidate_invariant, model_response = model.generate_candidate_invariant(program=program)
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
                'report': report.to_dict(),
                'model_response': model_response,
            }
            
            final_results['results'].append(task_result)
        
        return final_results

    def save_metrics(self, metrics_by_model: Dict[str, Dict], metrics_dir: Path) -> None:
        """
        Save and print a metrics csv for all models, where each row is a model (nickname), and each column is a metric.
        """
        import pandas as pd

        # Compose big tables across all models
        rows_with_gen = []
        rows_without_gen = []
        for nickname, metrics in metrics_by_model.items():
            row_with_gen = {'Model': nickname}
            row_with_gen.update(metrics['metrics_with_gen'])
            rows_with_gen.append(row_with_gen)

            row_without_gen = {'Model': nickname}
            row_without_gen.update(metrics['metrics_without_gen'])
            rows_without_gen.append(row_without_gen)

        df_with_gen = pd.DataFrame(rows_with_gen)
        df_without_gen = pd.DataFrame(rows_without_gen)

        df_with_gen.to_csv(metrics_dir / "all_models_metrics_with_gen.csv", index=False)
        df_without_gen.to_csv(metrics_dir / "all_models_metrics_without_gen.csv", index=False)

        print("Metrics WITH model generation time (with_gen):")
        print(df_with_gen.to_string(index=False))
        print("\nMetrics WITHOUT model generation time (without_gen):")
        print(df_without_gen.to_string(index=False))

    def run(self, save_plots: bool = True):
        """Run evaluation for all configured models."""
        metrics_dir = EXPERIMENTS_DIR / self.full_exp_id / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        all_metrics_by_model = {}
        
        for model_config in self.model_configs:
            # Use HuggingFaceModel instead of Model
            model = HuggingFaceModel(model_config=model_config)
            working_dir = EXPERIMENTS_DIR / self.full_exp_id / f"{model.nickname}"
            working_dir.mkdir(parents=True, exist_ok=True)
            final_results = self.evaluate_model(model, working_dir)
            results_filename = f"{model.nickname}_results.json"
            model_results_path = working_dir / results_filename
            save_as_json(final_results, model_results_path)
            
            if self.config.compute_metrics:
                metrics = InvBenchMetrics.calculate_metrics(results_path=model_results_path)
                all_metrics_by_model[model.nickname] = metrics
                if save_plots:
                    plot_path = metrics_dir / f"{model.nickname}_scatter_plot.html"
                    InvBenchMetrics.plot_verification_vs_baseline(
                        results_path=model_results_path,
                        model_name=model.nickname,
                        baseline_name=self.baseline_name,
                        split_name=self.config.data_split,
                        metrics=metrics,
                        plot_path=plot_path
                    )

        self.save_metrics(metrics_by_model=all_metrics_by_model, metrics_dir=metrics_dir)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Evaluate HuggingFace models on InvBench dataset")
    parser.add_argument("--project_name", type=str, default="rlinv-hf", required=False, help="Project name")
    parser.add_argument("--exp_id", type=str, default="hf_eval", help="Experiment ID, /configs/models_configs/<exp_id>.json is expected.")
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
    parser.add_argument("--baseline_is_timeout", action="store_true", 
                       help="Use baseline timeout instead of default timeout (default: False)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    evaluator_config = InvBenchHFEvaluatorConfig(
        project_name=args.project_name,
        exp_id=args.exp_id,
        models_configs_path=f"configs/models_configs/{args.exp_id}.json",
        baseline_dir=args.baseline_dir,
        data_split=args.data_split,
        limit=int(args.limit),
        default_timeout_seconds=args.default_timeout_seconds,
        property_kind=args.property_kind,
        prefix=args.prefix if args.prefix else None,
        suffix=args.suffix if args.suffix else None,
        compute_metrics=args.compute_metrics,
        baseline_is_timeout=args.baseline_is_timeout,
    )
    evaluator = InvBenchHFEvaluator(config=evaluator_config)
    evaluator.run(save_plots=True)

