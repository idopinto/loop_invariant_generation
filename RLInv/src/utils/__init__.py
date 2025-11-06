# """
# Core utility modules for loop invariant generation.
# """

# # Core classes that don't have external dependencies
# from .predicate import Predicate
# from .program import Program, AssertionPointAttributes
# from .task import Task
# from .rewriter import Rewriter
# from .plain_verifier import run_uautomizer, VerifierCallReport
# # Optional imports that may have external dependencies
# try:
#     from .prompter import Prompter
#     _PROMpter_AVAILABLE = True
# except ImportError:
#     _PROMpter_AVAILABLE = False

# try:
#     from .verifier import Verifier, Result
#     _VERIFIER_AVAILABLE = True
# except ImportError:
#     _VERIFIER_AVAILABLE = False

# try:
#     from .generate_yml_files import generate_yml_files
#     _GENERATE_YML_AVAILABLE = True
# except ImportError:
#     _GENERATE_YML_AVAILABLE = False

# __all__ = [
#     'Predicate',
#     'Program', 
#     'AssertionPointAttributes',
#     'Task',
#     'Rewriter',
#     'run_uautomizer',
#     'VerifierCallReport',
#     'Decision',
# ]

# # Add optional exports if available
# if _PROMpter_AVAILABLE:
#     __all__.append('Prompter')
# if _VERIFIER_AVAILABLE:
#     __all__.extend(['Verifier', 'Result'])
# if _GENERATE_YML_AVAILABLE:
#     __all__.append('generate_yml_files')
