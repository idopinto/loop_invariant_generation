from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.utils.plain_verifier import run_uautomizer, VerifierCallReport
from src.utils.program import Program
from src.utils.predicate import Predicate
from src.eval.decision_procedure_report import DecisionProcedureReport
from src.utils.validate import syntactic_validation

class DecisionProcedure:
    def __init__(self, program: Program, target_property_file_path: Path, code_dir: Path, root_dir: Path, timeout_seconds: float = 600.0):
        self.program = program
        self.root_dir = root_dir
        self.target_property_file_path = target_property_file_path # "unreach-call.prp"
        # Get the target assert from the program's assertions
        if self.program.assertions:
            self.target_assert = program.assertions[0]  # Assuming first assert is the target
        else:
            self.target_assert = None   
        self.code_dir = code_dir
        
        # Create reports directory
        self.reports_dir = Path(code_dir).parent / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.uautomizer_executable_path = root_dir / "tools" / "uautomizer" / "Ultimate.py"
    
    def run_verifier(self, program_str: str, property_file_path: Path, timeout_seconds: float, kind: str):
        program_path = self.code_dir / f"code_for_{kind}.c"
        with open(program_path, 'w') as out_file:
            out_file.write(program_str)
        verifier_report: VerifierCallReport = run_uautomizer(
            program_path=program_path, 
            property_file_path=property_file_path,
            reports_dir=self.reports_dir,
            timeout_seconds=timeout_seconds,
            uautomizer_path=self.uautomizer_executable_path
        )
        return verifier_report
    
    def decide(self, candidate_invariant: Predicate, model_gen_time: float = 0.0) -> DecisionProcedureReport:
        
        program_for_correctness = self.program.get_program_with_assertion(predicate=candidate_invariant, 
                                                     assumptions=[],
                                                     assertion_points={},
                                                     forGPT=False,
                                                     dump=False)

        program_for_usefullness = self.program.get_program_with_assertion(predicate=self.target_assert,
                                                                          assumptions=[candidate_invariant],
                                                                          assertion_points={},
                                                                          forGPT=False,
                                                                          dump=False)
        
        # Parallel evaluation: run both verifier queries concurrently
        # da = V(P, Ø, q): Check if q is an invariant
        # db = V(P, {q}, p*): Check if target property holds assuming q is true
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both verifier tasks
            correctness_future = executor.submit(
                self.run_verifier,
                program_str=program_for_correctness,
                property_file_path=self.target_property_file_path,
                timeout_seconds=self.timeout_seconds,
                kind="correctness"
            )
            
            usefulness_future = executor.submit(
                self.run_verifier,
                program_str=program_for_usefullness,
                property_file_path=self.target_property_file_path,
                timeout_seconds=self.timeout_seconds,
                kind="usefulness"
            )
            
            # Track results as they complete
            invariant_correctness_report = None
            invariant_usefulness_report = None
            
            # Use as_completed to process results as they arrive (enables short-circuiting DEC-FALSE)
            # DEC-FALSE: If db = F, we can decide F without waiting for da to complete
            for future in as_completed([correctness_future, usefulness_future]):
                result = future.result()
                if future == correctness_future:
                    invariant_correctness_report = result
                elif future == usefulness_future:
                    invariant_usefulness_report = result
                    # Short-circuit DEC-FALSE: if usefulness is Falsified, we can skip waiting for correctness
                    # and decide F immediately (DEC-FALSE doesn't require da)
                    if invariant_usefulness_report.decision == "FALSE":
                        # Try to cancel correctness if it's still running
                        if not correctness_future.done():
                            correctness_future.cancel()
                        # We have what we need for DEC-FALSE, break early
                        break
            
            # After loop: if correctness completed but wasn't captured, get it now
            if invariant_correctness_report is None and correctness_future.done():
                try:
                    invariant_correctness_report = correctness_future.result()
                except Exception:
                    pass  # If it was cancelled or failed, leave it as None
        
        decision_rule = ""
        # Apply decision calculus
        final_decision = "UNKNOWN"
        
        # DEC-FALSE: If db = F, decide F (short-circuit refutation)
        # This is a "short-circuit" because da doesn't need to be T to decide F
        if invariant_usefulness_report.decision == "FALSE":
            final_decision = "FALSE"
            decision_rule = "DEC-FALSE"
        
        # DEC_PROP: If da = T and db ∈ {T, U}, decide db
        # Rule DEC-PROP implements the provethen-use strategy: 
        # once the candidate invariant q is established, the outcome is exactly the verifier's
        # answer on the goal under the assumption q
        elif (invariant_correctness_report is not None and 
              invariant_correctness_report.decision == "TRUE" and 
              invariant_usefulness_report.decision in {"TRUE", "UNKNOWN"}):
            final_decision = invariant_usefulness_report.decision
            decision_rule = "DEC-PROP"
        
        # DEC-U: If da ≠ T and db ≠ F, decide U
        # Rule DEC-U gives explicit conditions for inconclusiveness:
        # the goal is not refuted under q and q is not established as an invariant
        elif (invariant_correctness_report is not None and 
              invariant_correctness_report.decision != "TRUE" and 
              invariant_usefulness_report.decision != "FALSE"):
            final_decision = "UNKNOWN"
            decision_rule = "DEC-U"
        # If correctness was cancelled (short-circuited), we already decided F above
        elif invariant_correctness_report is None:
            # This should only happen when DEC-FALSE was triggered
            # (decision already set to Falsified above)
            final_decision = "FALSE"
            decision_rule = "DEC-FALSE"
        
        # Calculate verification time: max of both runs since they execute in parallel
        # Use 0 if correctness was cancelled (short-circuited)
        correctness_time = invariant_correctness_report.time_taken if invariant_correctness_report else 0.0
        usefulness_time = invariant_usefulness_report.time_taken if invariant_usefulness_report else 0.0
        verification_time_taken = max(correctness_time, usefulness_time)
        # total_time_taken will be set to verification_time_taken + model_generation_time by caller
        final_report = DecisionProcedureReport(
            final_decision=final_decision,
            decision_rule=decision_rule,
            program=self.program,
            target_assert=self.target_assert,
            target_property_file_path=self.target_property_file_path,
            candidate_invariant=candidate_invariant,
            syntactic_validation_result=True,
            invariant_correctness_report=invariant_correctness_report,
            invariant_usefulness_report=invariant_usefulness_report,
            verification_time_taken=verification_time_taken,
            model_generation_time=model_gen_time,
        )  
        return final_report
    
    def run(self, candidate_invariant: Predicate, model_gen_time: float) -> DecisionProcedureReport:
        final_report = DecisionProcedureReport(model_generation_time=model_gen_time)
        is_valid = syntactic_validation(candidate_invariant.content)
        # is_logicaly_equivalent = check_semantic_equivalence(candidate_invariant.content, self.target_assert.content)
        print(f"The candidate invariant is valid: {is_valid}")
        # print(f"The candidate invariant is logically equivalent to the target assert: {is_logicaly_equivalent}")
        if is_valid: # and not is_logicaly_equivalent:
           final_report = self.decide(candidate_invariant, model_gen_time)
           final_report.total_time_taken = final_report.verification_time_taken + model_gen_time
        # save the final report to a json file
        report_file_path = self.reports_dir / "decision_report.json"
        final_report.save_json(report_file_path)
        print(f"Decision report saved to:\n\t {report_file_path.relative_to(self.root_dir)}")
        return final_report
    