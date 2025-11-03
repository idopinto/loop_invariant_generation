
from pathlib import Path
from shutil import copy
from typing import List, Dict, Optional
from src.eval.model import Model
import json
import time
import sys
import argparse
from dataclasses import dataclass
# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils import Task, Rewriter, Program
from src.eval.decision_procedure import DecisionProcedure
from src.eval.decision_procedure_report import DecisionProcedureReport


@dataclass
class InvBenchEvaluatorConfig:
    working_dir: Path
    tasks: List[Task]
    model: Model
    baseline_results: Optional[List[Dict]] = None
    default_timeout_seconds: int = 600
    root_dir: Path = Path('/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv')
    property_kind: str = "unreach"
    
class InvBenchEvaluator:
    def __init__(self, config: InvBenchEvaluatorConfig):
        self.config = config
        self.config.working_dir.mkdir(parents=True, exist_ok=True)
        self.final_results_file_path = self.config.working_dir / "final_results.json"
        self.evaluators = []
        self.baseline_timing_lookup = {r["base_filename"]: r["baseline_timing"] for r in self.config.baseline_results}
        # Create evaluators for each task
        for i, task in enumerate(self.config.tasks):
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

            r = Rewriter(c_program_path)
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
        
        for i, evaluator_data in enumerate(self.evaluators):
            task = evaluator_data['task']
            program = evaluator_data['program']
            decision_procedure = evaluator_data['decision_procedure']
            print(f"\n--- Evaluating task {i+1}/{len(self.evaluators)}: {task.source_code_path.name} ---")
            
            # Generate candidate invariant using the model (track time for paper compliance)
            model_gen_start = time.perf_counter()
            candidate_invariant = self.config.model.generate_candidate_invariant(program=program)
            model_gen_time = time.perf_counter() - model_gen_start  

            baseline_time = self.baseline_timing_lookup.get(task.yml_file.stem, 0.0)

            print("Running decision procedure in parallel.")
            # Evaluate the candidate invariant
            final_report = decision_procedure.run(candidate_invariant, model_gen_time)
            if final_report.syntactic_validation_result:
                final_report.total_time_taken = final_report.verification_time_taken + model_gen_time                
                print(f"""Decision Procedure summary: \n
                    '\t Target assert: {decision_procedure.target_assert}\n
                    '\t Candidate invariant: {candidate_invariant}\n
                    '\t valid invariant: {final_report.syntactic_validation_result}\n
                    '\t final decision: {final_report.final_decision.name}\n
                    '\t Decision rule: {final_report.decision_rule}\n
                    '\t Decision Procedure Timeout (UAutomizer baseline): {baseline_time:.2f}s\n
                    '\t Model generation time: {model_gen_time:.2f}s\n
                    '\t Correctness: {final_report.invariant_correctness_report.decision.name} - {final_report.invariant_correctness_report.time_taken:.2f}s\n
                    '\t Usefulness: {final_report.invariant_usefulness_report.decision.name} - {final_report.invariant_usefulness_report.time_taken:.2f}s\n
                    '\t Verification time (max(correctness, usefulness)): {final_report.verification_time_taken:.2f}s\n
                    '\t Total time (verification + model generation): {final_report.total_time_taken:.2f}s\n""")
            else:
                print(f"""Decision Procedure summary: \n
                    '\t Target assert: {decision_procedure.target_assert}\n
                    '\t Candidate invariant: {candidate_invariant}\n
                    '\t valid invariant: {final_report.syntactic_validation_result}\n
                    '\t final decision: {final_report.final_decision.name}\n""")
            
            # Create result entry for final report
            task_result = {
                'task_index': i,
                'task_name': task.yml_file.stem,
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
        self.save_final_results(final_results)
        return final_results
    
    def save_final_results(self, final_results: dict) -> None:
        with open(self.final_results_file_path, 'w') as f:
            json.dump(final_results, f, indent=2)
        # print(f"\nFinal results saved to:\n\t {self.final_results_file_path}")