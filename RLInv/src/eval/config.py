"""
Configuration module for evaluation.

Centralizes all configuration, constants, and prompts for the evaluation pipeline.
"""
from dataclasses import dataclass, field
from typing import Dict

import weave

# Constants
LOCATION_LABELS = [chr(ord('A') + i) for i in range(26)]

# Default prompts
DEFAULT_SYSTEM_PROMPT = """You are an expert C programmer and highly profiecient in generating strong loop invariants for C programs that accelerates traditional verifiers. """

DEFAULT_USER_PROMPT_TEMPLATE = """Generate a single candidate invariant for a given C program. you can place it at any of the marked lines with // Line <line_char>, choose the most beneficial location:
```c
{program}
```
Format:
assert(<invariant>); // Line <line_char>

Example:
assert(a > 0 && a < 10); // Line A
"""


@dataclass
class SamplingParams:
    """Parameters for model sampling/generation."""
    max_new_tokens: int = 2048
    do_sample: bool = True
    temperature: float = 0.6

    def to_dict(self) -> Dict:
        return {
            "max_new_tokens": self.max_new_tokens,
            "do_sample": self.do_sample,
            "temperature": self.temperature
        }


@dataclass
class EvalConfig:
    """
    Configuration for the evaluation pipeline.
    
    Centralizes all configuration options including model settings,
    verification parameters, and runtime options.
    """
    # Model configuration
    base_model_name: str = "openai/gpt-oss-20b"
    peft_model_id: str = "gpt-oss-20b-rlinv-sft-sep"
    is_lora: bool = True
    reasoning_effort: str = "low"
    sampling_params: SamplingParams = field(default_factory=SamplingParams)
    
    # Verification configuration
    arch: str = "32bit"
    timeout: float = 600.0
    uautomizer_version: str = "25"
    
    # When True, use baseline timing as timeout for verification
    # This ensures fair comparison by giving the model-assisted verification
    # the same time budget as the baseline
    baseline_is_timeout: bool = True
    
    # Dataset configuration
    dataset_name: str = "idopinto/invbench-evaluation-uautomizer25-k1"
    weave_team: str = "ip-ai"
    
    # Runtime flags
    testing: bool = True
    
    # Prompts (initialized in __post_init__)
    system_prompt: weave.StringPrompt = field(default=None, repr=False)
    user_prompt_template: weave.StringPrompt = field(default=None, repr=False)
    
    def __post_init__(self):
        """Initialize Weave prompts after dataclass creation."""
        if self.system_prompt is None:
            self.system_prompt = weave.StringPrompt(DEFAULT_SYSTEM_PROMPT)
        if self.user_prompt_template is None:
            self.user_prompt_template = weave.StringPrompt(DEFAULT_USER_PROMPT_TEMPLATE)
    
    def get_dataset_name(self) -> str:
        """Get dataset name with test suffix if testing mode is enabled."""
        name = self.dataset_name
        if self.testing:
            name = f"{name}-test"
        return name
    
    def get_project_name(self, split: str) -> str:
        """Get project name with optional test suffix."""
        name = f"inv-gen-eval-{split}"
        if self.testing:
            name = f"{name}-test"
        return name
    
    def get_run_name(self, split: str) -> str:
        """Get run name for evaluation."""
        return f"{self.peft_model_id}-{split}"
    
    def get_model_display_name(self) -> str:
        """Get display name for the model including reasoning effort."""
        return f"{self.peft_model_id}-{self.reasoning_effort}"


def get_default_config() -> EvalConfig:
    """Get the default evaluation configuration."""
    return EvalConfig()

