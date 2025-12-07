"""
Evaluation module for loop invariant generation.

This module provides the evaluation pipeline for assessing model-generated
loop invariants using formal verification tools.
"""

from src.eval.config import EvalConfig, get_default_config
from src.eval.data import get_evaluation_dataset, preprocess_example
from src.eval.decision_procedure import DecisionProcedure, DecisionProcedureReport
from src.eval.model import InvariantGeneratorModel, create_invariant_generator, load_model
from src.eval.scorer import InvariantScorer, ResultCollector
from src.eval.wandb_utils import upload_plot_to_wandb

__all__ = [
    # Config
    "EvalConfig",
    "get_default_config",
    # Data
    "get_evaluation_dataset",
    "preprocess_example",
    # Model
    "InvariantGeneratorModel",
    "create_invariant_generator",
    "load_model",
    # Scoring
    "InvariantScorer",
    "ResultCollector",
    "DecisionProcedure",
    "DecisionProcedureReport",
    # Utilities
    "upload_plot_to_wandb",
]
