
from pathlib import Path
from shutil import copy
from typing import List, Dict, Optional
from src.eval.model import Model
import json
import time
import sys
import argparse

# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils import Task, Rewriter, Program
from src.eval.decision_procedure import DecisionProcedure
UAUTOMIZER_EXECUTABLE_PATH = '/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/tools/uautomizer/Ultimate.py'

    
class InvBenchEvaluator:
    def __init__(self, working_dir: Path, tasks: List[Task], model: Model, baseline_results: Optional[List[Dict]] = None):
        self.tasks = tasks
        self.model = model
        self.working_dir = working_dir
        self.evaluators = []
        
        # Create baseline timing lookup: base_filename -> baseline_timing (in seconds)
        # Use exact baseline timing as timeout (per paper requirement)
        self.baseline_timing_lookup = {}
        if baseline_results:
            for r in baseline_results:
                base_filename = r.get("base_filename", "")
                baseline_timing = r.get("baseline_timing", 0.0)
                if base_filename and baseline_timing > 0:
                    # Store original baseline timing (used as timeout, with minimum of 0.1 seconds)
                    self.baseline_timing_lookup[base_filename] = max(0.1, baseline_timing)
        else:
            self.baseline_timing_lookup = {}
        
        # Create evaluators for each task
        for i, task in enumerate(tasks):
            # Create a unique subdirectory for each task within the main working directory
            task_dir = working_dir / f"task_{i}_{task.source_code_path.stem}"
            task_dir.mkdir(parents=True, exist_ok=True)
            
            code_dir = task_dir / "code"
            code_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy over the c file and the property file
            c_program_path = code_dir / "base.c"
            target_property_path = code_dir / "property"
            
            copy(task.source_code_path, c_program_path)
            copy(task.property_path, target_property_path)

            r = Rewriter(c_program_path)
            program = Program(r.lines_to_verify, r.replacement)
            
            # Get timeout for this task: use baseline timing if available, otherwise default to 30 seconds
            # Use yml_file.stem to match baseline's base_filename (which uses yml_file.stem)
            task_base_filename = task.yml_file.stem
            baseline_time = self.baseline_timing_lookup.get(task_base_filename, 0.0)
            timeout_seconds = baseline_time if baseline_time > 0 else 30.0
            
            decision_procedure = DecisionProcedure(
                program, 
                target_property_path, 
                code_dir, 
                UAUTOMIZER_EXECUTABLE_PATH,
                default_timeout_seconds=timeout_seconds
            )
            
            # Store evaluator components for this task
            self.evaluators.append({
                'task': task,
                'working_dir': task_dir,
                'code_dir': code_dir,
                'program': program,
                'decision_procedure': decision_procedure,
                'baseline_time': baseline_time
            })

    
    def evaluate(self) -> dict:
        """
        Evaluate all tasks using model-generated candidate invariants.
        
        Returns:
            Dictionary containing final results and individual reports
        """
        final_results = {
            'evaluation_timestamp': time.strftime('%Y%m%d_%H%M%S'),
            'model_path_or_name': self.model.model_path_or_name,
            'total_tasks': len(self.tasks),
            'results': []
        }
        
        for i, evaluator_data in enumerate(self.evaluators):
            task = evaluator_data['task']
            program = evaluator_data['program']
            decision_procedure = evaluator_data['decision_procedure']
            
            print(f"\n--- Evaluating task {i+1}/{len(self.tasks)}: {task.source_code_path.name} ---")
            
            # Generate candidate invariant using the model (track time for paper compliance)
            model_gen_start = time.perf_counter()
            candidate_invariant = self.model.generate_candidate_invariant(program=program)
            model_gen_time = time.perf_counter() - model_gen_start
            
            print(f"Candidate invariant: {candidate_invariant}")
            print(f"Model generation time: {model_gen_time:.2f}s")
            baseline_time = evaluator_data.get('baseline_time', 0.0)
            print(f"Timeout (UAutomizer baseline): {baseline_time:.2f}s")

            print("Running decision procedure in parallel.")
            # Evaluate the candidate invariant
            final_report = decision_procedure.run(candidate_invariant)
            # Store both timing values: verification time (without model) and total time (with model)
            final_report.model_generation_time = model_gen_time
            final_report.total_time_taken = final_report.verification_time_taken + model_gen_time
            
            # Print verification time details
            correctness_time = final_report.invariant_correctness_report.time_taken if final_report.invariant_correctness_report else 0.0
            usefulness_time = final_report.invariant_usefulness_report.time_taken if final_report.invariant_usefulness_report else 0.0

            print(f"Verification time - Correctness: {correctness_time:.2f}s, Usefulness: {usefulness_time:.2f}s, Max: {final_report.verification_time_taken:.2f}s")
            print(f"Total time (verification + model generation): {final_report.total_time_taken:.2f}s")
            
            # Create result entry for final report
            # Use yml_file.stem for task_name to match baseline's base_filename
            task_result = {
                'task_index': i,
                'task_name': task.yml_file.stem,  # Use YML stem to match baseline base_filename
                'task_path': str(task.source_code_path),
                'property_path': str(task.property_path),
                'arch': task.arch,
                'candidate_invariant': {
                    'content': candidate_invariant.content,
                    'line_number': candidate_invariant.line_number
                },
                'report': final_report.to_dict()
            }
            
            final_results['results'].append(task_result)
        
        # Save final results
        self.working_dir.mkdir(parents=True, exist_ok=True)
        final_file_path = self.working_dir / f"final_results_{final_results['evaluation_timestamp']}.json"
        with open(final_file_path, 'w') as f:
            json.dump(final_results, f, indent=2)
        
        print(f"\nFinal results saved to: {final_file_path}")
        
        return final_results



def load_dataset(dataset_path: Path, property_kind: str = "unreach", limit: int = None) -> List[Task]:
    tasks = []
    print(f"Loading dataset from: {dataset_path}")
    for yml_file in dataset_path.glob("*.yml"):
        # print(yml_file)
        if limit is not None and len(tasks) >= limit:
            break
        task = Task(yml_file_path=yml_file, property_kind=property_kind)
        # print(task)
        tasks.append(task)
    return tasks

def load_baseline_results(baseline_file: Path) -> List[Dict]:
    """Load baseline results from JSON file."""
    if not baseline_file.exists():
        print(f"Warning: Baseline file not found at {baseline_file}, using default timeouts")
        return []
    try:
        with open(baseline_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load baseline results from {baseline_file}: {e}, using default timeouts")
        return []

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate model on loop invariant generation tasks"
    )
    parser.add_argument(
        "--model_name_or_path",
        type=str,
        required=True,
        help="Model name or path"
    )
    parser.add_argument(
        "--data_split",
        type=str,
        required=True,
        choices=["easy", "hard"],
        help="Data split: easy or hard"
    )
    parser.add_argument(
        "--exp_id",
        type=str,
        required=True,
        help="Experiment ID"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of tasks to evaluate (optional)"
    )
    
    args = parser.parse_args()
    
    root_dir = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv")
    dataset_path = root_dir / "dataset" / "evaluation" / args.data_split / "yml"
    baseline_file = root_dir / "dataset" / "evaluation" / args.data_split / "baseline_results.json"
    experiments_dir = root_dir / "experiments" / f"exp_{args.exp_id}"
    # Save results per-model under a dedicated folder: <model>_results
    def _sanitize(name: str) -> str:
        return name.replace("/", "_").replace(" ", "_")
    working_dir = experiments_dir / f"{_sanitize(args.model_name_or_path)}_results"
    
    tasks = load_dataset(dataset_path, property_kind="unreach", limit=args.limit)
    
    # Load baseline results to get per-task timeouts
    baseline_results = load_baseline_results(baseline_file)
    if baseline_results:
        print(f"Loaded {len(baseline_results)} baseline timing results")
    else:
        print("No baseline results loaded, using default timeout of 30 seconds per task")
    
    model = Model(model_path_or_name=args.model_name_or_path)
    evaluator = InvBenchEvaluator(working_dir=working_dir, tasks=tasks, model=model, baseline_results=baseline_results)
    evaluator.evaluate()
    