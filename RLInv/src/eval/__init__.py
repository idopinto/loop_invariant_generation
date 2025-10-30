"""
Evaluation module for loop invariant generation.
"""

# Use lazy imports to avoid circular import issues
__all__ = [
    'InvBenchEvaluator',
    'DecisionProcedure', 
    'DecisionProcedureReport'
]

def __getattr__(name):
    """Lazy import to avoid circular imports."""
    if name == 'InvBenchEvaluator':
        from .evaluate import InvBenchEvaluator
        return InvBenchEvaluator
    elif name == 'DecisionProcedure':
        from .decision_procedure import DecisionProcedure
        return DecisionProcedure
    elif name == 'DecisionProcedureReport':
        from .decision_procedure_report import DecisionProcedureReport
        return DecisionProcedureReport
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
