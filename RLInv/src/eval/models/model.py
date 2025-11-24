
from src.utils.program import Program
from src.utils.predicate import Predicate
from together import Together
from dotenv import load_dotenv
from typing import Tuple, Dict
import os
import re
from src.eval.models.model_utils import build_prompt, parse_response, format_program_with_labels, label_assertion_points

load_dotenv()

class Model:
    def __init__(self, model_config: Dict):
        self.model_config = model_config    
        self.nickname = model_config["model_path_or_name"].split("/")[-1] + "-" + model_config["sampling_params"]["reasoning_effort"]
        if self.model_config["client"] == "together":
            self.client = Together(api_key=os.getenv("TOGETHER_API_KEY"))
        else:
            raise ValueError(f"Unsupported client: {self.model_config["client"]}")

    def _call_model_api(self, system_msg: str, user_msg: str) -> str:
        """Call the Together API and return response content."""
        # print(f"\nSystem msg:\n{system_msg}")
        # print(f"\nUser msg:\n{user_msg}")
        if self.model_config["client"] == "openai":
            input_msg = system_msg + "\n\n" + user_msg
            result = self.client.responses.create(
            model=self.model_config["model_path_or_name"],
            input=input_msg,
            **self.model_config["sampling_params"]
        )
            return {"reasoning": result.reasoning.summary, "raw_response": result.output_text, "usage": result.usage}
        else:
            response = self.client.chat.completions.create(
                model=self.model_config["model_path_or_name"],
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ],
                **self.model_config["sampling_params"]
            )
            reasoning = response.choices[0].message.reasoning
            raw_response = response.choices[0].message.content
            usage = response.usage
            print("\n" + "="*80)
            for dot in reasoning.split('.'):
                print(f"{dot.strip()}.")
            print("\n" + "="*80)
            print(f"Raw response: {raw_response}")
            print("\n" + "="*80)
            print(f"Usage: {usage}")
            print("\n" + "="*80)
            return {"reasoning": reasoning, "raw_response": raw_response, "usage": usage.dict()}
    
    def generate_candidate_invariant(self, program: Program) -> Tuple[Predicate, dict]:
        """Generate a candidate invariant using the model following InvBench approach."""
        assertion_points = program.assertion_points
        if not assertion_points:
            print("Warning: No assertion points found, using line 0 as default")
            return Predicate(content="1 > < 1", line_number=0), {} # dummy invalid invariant
        
        try:
            labeled_points, name_to_line = label_assertion_points(assertion_points)
            sorted_lines = sorted(assertion_points.keys())
            formatted_program = format_program_with_labels(program=program, labeled_points=labeled_points)
            system_msg, user_msg = build_prompt(formatted_program=formatted_program, assertion_points=assertion_points, labeled_points=labeled_points, sorted_lines=sorted_lines)
            model_response = self._call_model_api(system_msg, user_msg)
            predicate, line_num = parse_response(response_content=model_response.get("raw_response", "") or "", name_to_line=name_to_line, sorted_lines=sorted_lines)
            if predicate is None or line_num is None:
                raise ValueError(f"Could not parse invariant from response: {model_response.get('raw_response', '')[:200]}")
            
            return Predicate(content=re.sub(r'\s+', ' ', predicate).strip(), line_number=line_num), model_response
        except Exception as e:
            print(f"Error generating invariant: {e}")
            fallback_line = sorted(assertion_points.keys())[0] if assertion_points else 0
            return Predicate(content="1 > < 1", line_number=fallback_line), {} # dummy invalid invariant

