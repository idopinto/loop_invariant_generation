"""
HuggingFace Model for local inference with GPT-OSS models.
Supports loading models directly from HuggingFace, including PEFT/LoRA adapters.
Handles Harmony format parsing for GPT-OSS output.
"""

import torch
import re
from typing import Dict, Tuple, Optional
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

from src.utils.program import Program
from src.utils.predicate import Predicate
from src.eval.models.model_utils import (
    build_prompt,
    parse_response,
    format_program_with_labels,
    label_assertion_points,
)


def parse_dtype(dtype_str: str) -> torch.dtype:
    """Convert string dtype to torch dtype."""
    dtype_map = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    return dtype_map.get(dtype_str, torch.bfloat16)


def parse_harmony_output(raw_output: str) -> Dict[str, Optional[str]]:
    """
    Parse Harmony format output from GPT-OSS models.
    
    Harmony format structure:
    - Analysis/reasoning: <|channel|>analysis<|message|>...<|end|>
    - Final answer: <|channel|>final<|message|>...<|return|> or <|end|>
    
    Returns:
        dict with 'reasoning' and 'raw_response' keys.
        'raw_response' is None if final channel not found.
    """
    # Try to extract final channel
    final_pattern = r'<\|channel\|>final<\|message\|>(.*?)(?:<\|return\|>|<\|end\|>|$)'
    final_match = re.search(final_pattern, raw_output, re.DOTALL)
    
    # Extract analysis/reasoning if present
    analysis_pattern = r'<\|channel\|>analysis<\|message\|>(.*?)<\|end\|>'
    analysis_match = re.search(analysis_pattern, raw_output, re.DOTALL)
    
    reasoning = analysis_match.group(1).strip() if analysis_match else ""
    raw_response = final_match.group(1).strip() if final_match else None
    
    return {"reasoning": reasoning, "raw_response": raw_response}


class HuggingFaceModel:
    """
    HuggingFace model wrapper for local inference.
    Compatible with the evaluation pipeline's Model interface.
    """
    
    def __init__(self, model_config: Dict):
        self.model_config = model_config
        self.nickname = self._build_nickname()
        
        # Load tokenizer and model
        self.tokenizer = self._load_tokenizer()
        self.model = self._load_model()
        
        print(f"HuggingFaceModel initialized: {self.nickname}")
        print(f"  Model: {model_config['model_path_or_name']}")
        print(f"  Device: {next(self.model.parameters()).device}")
    
    def _build_nickname(self) -> str:
        """Build a nickname for the model."""
        model_name = self.model_config["model_path_or_name"].split("/")[-1]
        # Add suffix if available (e.g., sampling params info)
        suffix = self.model_config.get("sampling_params", {}).get("max_new_tokens", "")
        if suffix:
            return f"{model_name}-hf-{suffix}tok"
        return f"{model_name}-hf"
    
    def _load_tokenizer(self) -> AutoTokenizer:
        """Load tokenizer from HuggingFace."""
        model_path = self.model_config["model_path_or_name"]
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        
        # Ensure pad token is set
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        return tokenizer
    
    def _load_model(self) -> AutoModelForCausalLM:
        """Load model from HuggingFace, with optional PEFT adapter support."""
        model_path = self.model_config["model_path_or_name"]
        is_peft = self.model_config.get("is_peft", False)
        base_model_path = self.model_config.get("base_model", None)
        
        # Build model kwargs
        model_kwargs = self._build_model_kwargs()
        
        if is_peft and base_model_path:
            # Load base model first, then apply PEFT adapter
            print(f"Loading base model: {base_model_path}")
            model = AutoModelForCausalLM.from_pretrained(base_model_path, **model_kwargs)
            
            print(f"Loading PEFT adapter: {model_path}")
            model = PeftModel.from_pretrained(model, model_path)
            
            print("Merging and unloading adapter...")
            model = model.merge_and_unload()
        else:
            # Load model directly
            print(f"Loading model: {model_path}")
            model = AutoModelForCausalLM.from_pretrained(model_path, **model_kwargs)
        
        model.eval()
        return model
    
    def _build_model_kwargs(self) -> Dict:
        """Build kwargs for model loading."""
        config_kwargs = self.model_config.get("model_kwargs", {})
        
        kwargs = {
            "device_map": config_kwargs.get("device_map", "auto"),
            "use_cache": True,
        }
        
        # Handle dtype
        dtype_str = config_kwargs.get("torch_dtype", "bfloat16")
        kwargs["torch_dtype"] = parse_dtype(dtype_str)
        
        # Handle attention implementation
        if "attn_implementation" in config_kwargs:
            kwargs["attn_implementation"] = config_kwargs["attn_implementation"]
        
        return kwargs
    
    def _build_messages(self, system_msg: str, user_msg: str) -> list:
        """
        Build messages in the format expected by GPT-OSS chat template.
        
        The chat template expects:
        - 'developer' role for system/instruction messages (NOT 'system')
        - 'user' role for user messages
        """
        return [
            {"role": "developer", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]
    
    def _generate(self, system_msg: str, user_msg: str) -> Dict:
        """
        Generate response using local inference.
        
        Returns dict with 'reasoning', 'raw_response', and 'usage' keys.
        """
        messages = self._build_messages(system_msg, user_msg)
        
        # Apply chat template
        input_ids = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt"
        ).to(self.model.device)
        
        # Get generation parameters
        sampling_params = self.model_config.get("sampling_params", {})
        gen_kwargs = {
            "max_new_tokens": sampling_params.get("max_new_tokens", 512),
            "do_sample": sampling_params.get("do_sample", False),
            "pad_token_id": self.tokenizer.pad_token_id,
        }
        
        # Add optional sampling parameters
        if gen_kwargs["do_sample"]:
            gen_kwargs["temperature"] = sampling_params.get("temperature", 0.7)
            gen_kwargs["top_p"] = sampling_params.get("top_p", 0.9)
        
        # Generate
        with torch.inference_mode():
            output_ids = self.model.generate(input_ids, **gen_kwargs)
        
        # Decode full output
        full_output = self.tokenizer.decode(output_ids[0], skip_special_tokens=False)
        
        # Get only the new tokens (response part)
        input_length = input_ids.shape[1]
        new_tokens = output_ids[0][input_length:]
        response_text = self.tokenizer.decode(new_tokens, skip_special_tokens=False)
        
        # Parse Harmony format
        parsed = parse_harmony_output(response_text)
        
        # Build usage stats
        usage = {
            "prompt_tokens": input_length,
            "completion_tokens": len(new_tokens),
            "total_tokens": len(output_ids[0]),
        }
        
        return {
            "reasoning": parsed["reasoning"],
            "raw_response": parsed["raw_response"],
            "usage": usage,
            "full_output": full_output,  # For debugging
        }
    
    def generate_candidate_invariant(self, program: Program) -> Tuple[Predicate, dict]:
        """
        Generate a candidate invariant using the model.
        
        This follows the same interface as the Together AI-based Model class.
        """
        assertion_points = program.assertion_points
        if not assertion_points:
            print("Warning: No assertion points found, using line 0 as default")
            return Predicate(content="1 > < 1", line_number=0), {}  # dummy invalid invariant
        
        try:
            # Prepare prompt using existing utilities
            labeled_points, name_to_line = label_assertion_points(assertion_points)
            sorted_lines = sorted(assertion_points.keys())
            formatted_program = format_program_with_labels(
                program=program, labeled_points=labeled_points
            )
            system_msg, user_msg = build_prompt(
                formatted_program=formatted_program,
                assertion_points=assertion_points,
                labeled_points=labeled_points,
                sorted_lines=sorted_lines,
            )
            
            # Generate response
            model_response = self._generate(system_msg, user_msg)
            
            # Check if Harmony parsing succeeded
            raw_response = model_response.get("raw_response")
            if raw_response is None:
                print(f"Warning: Could not parse Harmony format from response")
                print(f"Full output: {model_response.get('full_output', '')[:500]}")
                fallback_line = sorted_lines[0] if sorted_lines else 0
                return Predicate(content="1 > < 1", line_number=fallback_line), model_response
            
            # Parse the response to extract predicate and line number
            predicate, line_num = parse_response(
                response_content=raw_response,
                name_to_line=name_to_line,
                sorted_lines=sorted_lines,
            )
            
            if predicate is None or line_num is None:
                print(f"Warning: Could not parse invariant from response: {raw_response[:200]}")
                fallback_line = sorted_lines[0] if sorted_lines else 0
                return Predicate(content="1 > < 1", line_number=fallback_line), model_response
            
            # Clean up predicate whitespace
            cleaned_predicate = re.sub(r'\s+', ' ', predicate).strip()
            
            # Build response dict for logging
            model_response_dict = {
                "system_prompt": system_msg,
                "user_prompt": user_msg,
                "raw_response": raw_response,
                "parsed_response": {
                    "predicate": cleaned_predicate,
                    "line_number": line_num,
                },
                "reasoning": model_response.get("reasoning", ""),
                "usage": model_response.get("usage", {}),
            }
            
            return Predicate(content=cleaned_predicate, line_number=line_num), model_response_dict
            
        except Exception as e:
            print(f"Error generating invariant: {e}")
            import traceback
            traceback.print_exc()
            fallback_line = sorted(assertion_points.keys())[0] if assertion_points else 0
            return Predicate(content="1 > < 1", line_number=fallback_line), {}

