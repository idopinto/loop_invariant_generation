import time
from pathlib import Path
from shutil import copy
from typing import List, Dict, Optional
from src.eval.model import Model
from dataclasses import dataclass
from src.utils.task import Task
from src.utils.rewriter import Rewriter
from src.utils.program import Program
from src.eval.decision_procedure import DecisionProcedure
from src.utils.utils import save_as_json
from tqdm import tqdm
@dataclass
class InvBenchEvaluatorConfig:
    working_dir: Path
    tasks: List[Task]
    model: Model
    root_dir: Path = Path('/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv')
    baseline_timing: Optional[List[Dict]] = None
    default_timeout_seconds: int = 600
    property_kind: str = "unreach"
    results_filename: str = "model_results.json"
    
class InvBenchEvaluator:
    def __init__(self, config: InvBenchEvaluatorConfig):
        self.config = config
        self.config.working_dir.mkdir(parents=True, exist_ok=True)
        self.final_results_file_path = self.config.working_dir / self.config.results_filename
        self.evaluators = []
        self.baseline_timing_lookup = {r["file"]: r["time"] for r in self.config.baseline_timing}
        self.create_evaluators()

    def create_evaluators(self) -> None:
        """
        Create evaluators for each task.
        """
        for i, task in tqdm(enumerate(self.config.tasks), total=len(self.config.tasks), desc="Creating evaluators"):
            # Create a unique subdirectory for each task within the main working directory
            task_dir = self.config.working_dir / f"task_{i}_{task.source_code_path.stem}"
            task_dir.mkdir(parents=True, exist_ok=True)
            
            code_dir = task_dir / "code"
            code_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy over the c file and the property file
            c_program_path = code_dir / "base.c"
            target_property_path = code_dir / "property"
            
            copy(task.source_code_path, c_program_path)
            copy(task.property_path, target_property_path)

            r = Rewriter(c_program_path, rewrite=True)
            program = Program(r.lines_to_verify, r.replacement)
            
            # Get timeout for this task: use baseline timing if available, otherwise default to 30 seconds
            # Use yml_file.stem to match baseline's base_filename (which uses yml_file.stem)
            task_base_filename = task.yml_file.stem
            baseline_time = self.baseline_timing_lookup.get(task_base_filename, 0.0)
            timeout_seconds = baseline_time if baseline_time > 0 else self.config.default_timeout_seconds
            
            decision_procedure = DecisionProcedure(
                program, 
                target_property_path, 
                code_dir, 
                root_dir=self.config.root_dir,
                timeout_seconds=timeout_seconds
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
            'model_path_or_name': self.config.model.model_path_or_name,
            'total_tasks': len(self.evaluators),
            'results': []
        }
        
        for i, evaluator_data in tqdm(enumerate(self.evaluators), total=len(self.evaluators), desc="Evaluating tasks"):
            task = evaluator_data['task']
            program = evaluator_data['program']
            decision_procedure = evaluator_data['decision_procedure']
            print(f"\n--- Evaluating task {i+1}/{len(self.evaluators)}: {task.source_code_path.name} ---")
            
            # Generate candidate invariant using the model (track time for paper compliance)
            model_gen_start = time.perf_counter()
            candidate_invariant = self.config.model.generate_candidate_invariant(program=program)
            model_gen_time = time.perf_counter() - model_gen_start  

            baseline_time = self.baseline_timing_lookup.get(task.yml_file.stem, 0.0)
            report = decision_procedure.run(candidate_invariant, model_gen_time)
            if report.syntactic_validation_result:
                report.total_time_taken = report.verification_time_taken + model_gen_time
                correctness_info = "N/A (short-circuited)" if report.invariant_correctness_report is None else f"{report.invariant_correctness_report.decision} - {report.invariant_correctness_report.time_taken:.2f}s"
                print(f"""Decision Procedure summary: \n
                    '\t Target assert: {decision_procedure.target_assert}\n
                    '\t Candidate invariant: {candidate_invariant}\n
                    '\t valid invariant: {report.syntactic_validation_result}\n
                    '\t final decision: {report.final_decision}\n
                    '\t Decision rule: {report.decision_rule}\n
                    '\t Decision Procedure Timeout (UAutomizer baseline timing): {baseline_time:.2f}s\n
                    '\t Model generation time: {model_gen_time:.2f}s\n
                    '\t Correctness: {correctness_info}\n
                    '\t Usefulness: {report.invariant_usefulness_report.decision} - {report.invariant_usefulness_report.time_taken:.2f}s\n
                    '\t Verification time (max(correctness, usefulness)): {report.verification_time_taken:.2f}s\n
                    '\t Total time (verification + model generation): {report.total_time_taken:.2f}s\n""")
            else:
                print(f"""Decision Procedure summary: \n
                    '\t Target assert: {decision_procedure.target_assert}\n
                    '\t Candidate invariant: {candidate_invariant}\n
                    '\t valid invariant: {report.syntactic_validation_result}\n
                    '\t final decision: {report.final_decision}\n""")
            
            # Create result entry for final report
            task_result = {
                'task_index': i,
                'task_name': task.yml_file.stem,
                'task_path': str(task.source_code_path),
                'property_path': str(task.property_path),
                'arch': task.arch,
                'candidate_invariant': {
                    'invariant': candidate_invariant.content,
                    'line': candidate_invariant.line_number
                },
                'report': report.to_dict()
            }
            
            final_results['results'].append(task_result)
        
        save_as_json(final_results, self.final_results_file_path)
        return final_results
    
