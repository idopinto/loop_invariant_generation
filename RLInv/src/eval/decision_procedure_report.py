from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import json
from src.utils.predicate import Predicate
from src.utils.program import Program
from src.utils.plain_verifier import VerifierCallReport, Decision

@dataclass
class DecisionProcedureReport:
    final_decision: Decision = Decision.Unknown
    program: Optional[Program] = None
    target_assert: Optional[Predicate] = None
    target_property_file_path: Optional[Path] = None
    candidate_invariant: Optional[Predicate] = None
    syntactic_validation_result: bool = False
    invariant_correctness_report: Optional[VerifierCallReport] = None
    invariant_usefulness_report: Optional[VerifierCallReport] = None
    total_time_taken: float = 0.0  # Includes model generation time
    verification_time_taken: float = 0.0  # Only verification time (without model generation)
    model_generation_time: float = 0.0  # Model inference/token generation time
    report_file_path: str = ""
    
    def to_dict(self) -> dict:
        """Convert the report to a dictionary for JSON serialization."""
        return {
            'final_decision': self.final_decision.name,
            'target_assert': {
                'content': self.target_assert.content,
                'line_number': self.target_assert.line_number
            } if self.target_assert else None,
            'target_property_file_path': str(self.target_property_file_path) if self.target_property_file_path else None,
            'candidate_invariant': {
                'content': self.candidate_invariant.content,
                'line_number': self.candidate_invariant.line_number
            } if self.candidate_invariant else None,
            'syntactic_validation_result': self.syntactic_validation_result,
            'invariant_correctness_report': self.invariant_correctness_report.to_dict() if self.invariant_correctness_report else None,
            'invariant_usefulness_report': self.invariant_usefulness_report.to_dict() if self.invariant_usefulness_report else None,
            'total_time_taken': self.total_time_taken,
            'verification_time_taken': self.verification_time_taken,
            'model_generation_time': self.model_generation_time,
            'report_file_path': self.report_file_path
        }
    
    def save_json(self, file_path: Path) -> None:
        """Save the report as a JSON file."""
        self.report_file_path = str(file_path)
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def from_json(cls, file_path: Path) -> 'DecisionProcedureReport':
        """Load a report from a JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Reconstruct nested objects
        target_assert = None
        if data.get('target_assert'):
            target_assert = Predicate(
                content=data['target_assert']['content'],
                line_number=data['target_assert']['line_number']
            )
        
        candidate_invariant = None
        if data.get('candidate_invariant'):
            candidate_invariant = Predicate(
                content=data['candidate_invariant']['content'],
                line_number=data['candidate_invariant']['line_number']
            )
        
        correctness_report = None
        if data.get('invariant_correctness_report'):
            correctness_report = VerifierCallReport(
                decision=Decision[data['invariant_correctness_report']['decision']],
                time_taken=data['invariant_correctness_report']['time_taken'],
                timeout=data['invariant_correctness_report']['timeout'],
                error=data['invariant_correctness_report']['error'],
                log_file_path=data['invariant_correctness_report']['log_file_path'],
                err_file_path=data['invariant_correctness_report']['err_file_path']
            )
        
        usefulness_report = None
        if data.get('invariant_usefulness_report'):
            usefulness_report = VerifierCallReport(
                decision=Decision[data['invariant_usefulness_report']['decision']],
                time_taken=data['invariant_usefulness_report']['time_taken'],
                timeout=data['invariant_usefulness_report']['timeout'],
                error=data['invariant_usefulness_report']['error'],
                log_file_path=data['invariant_usefulness_report']['log_file_path'],
                err_file_path=data['invariant_usefulness_report']['err_file_path']
            )
        
        return cls(
            final_decision=Decision[data['final_decision']],
            program=None,  # Program object is not serialized
            target_assert=target_assert,
            target_property_file_path=Path(data['target_property_file_path']) if data.get('target_property_file_path') else None,
            candidate_invariant=candidate_invariant,
            syntactic_validation_result=data['syntactic_validation_result'],
            invariant_correctness_report=correctness_report,
            invariant_usefulness_report=usefulness_report,
            total_time_taken=data.get('total_time_taken', 0.0),
            verification_time_taken=data.get('verification_time_taken', data.get('total_time_taken', 0.0)),  # Fallback for old format
            model_generation_time=data.get('model_generation_time', 0.0),
            report_file_path=data.get('report_file_path', str(file_path))
        )
