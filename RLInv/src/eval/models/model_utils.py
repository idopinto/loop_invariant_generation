from dataclasses import dataclass
from src.utils.program import Program
from copy import copy
import re

from typing import Dict
LOCATION_LABELS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"]

@dataclass
class ModelConfig:
    model_path_or_name: str
    sampling_params: Dict
    client: str 
    nickname: str

    @classmethod
    def from_dict(cls, model_config: Dict):
        return cls(
            client=model_config["client"],
            model_path_or_name=model_config["model_path_or_name"],
            sampling_params=model_config["sampling_params"],
            nickname=model_config["nickname"]
        )


def label_assertion_points(assertion_points: dict):
    """Label assertion points and create bidirectional mapping."""
    labeled, name_to_line = {}, {}
    for i, line_num in enumerate(sorted(assertion_points.keys())):
        if i < len(LOCATION_LABELS):
            label = LOCATION_LABELS[i]
            labeled[line_num] = label
            name_to_line[label] = line_num
    return labeled, name_to_line

def format_program_with_labels(program: Program, labeled_points: dict) -> str:
    """Format program with location labels and target assertion."""
    lines = copy(program.lines)
    for i, line in enumerate(lines):
        if line in program.replacement_for_GPT:
            lines[i] = program.replacement_for_GPT[line]
    for lemma in program.lemmas:
        lines[lemma.line_number] += f"\nassume({lemma.content});"
    for line_num, label in labeled_points.items():
        if line_num < len(lines):
            lines[line_num] += f"\n// Line {label}"
    if program.assertions:
        target = program.assertions[0]
        if target.line_number < len(lines):
            lines[target.line_number] += f"\nassert({target.content}); // Target property"
    return "\n".join(lines)

def build_prompt(formatted_program: str, assertion_points: dict, 
                    labeled_points: dict, sorted_lines: list):
    """Build system and user messages for the prompt."""
    locations = [f"  Line {labeled_points[ln]}: Line {ln} ({', '.join([a.name for a in assertion_points[ln]])})" 
                    for ln in sorted_lines]
    available_labels = ', '.join([labeled_points[ln] for ln in sorted_lines])
    user_msg = f"""Given the following C program, generate a loop invariant its location in the program from the available locations.
```c
{formatted_program}
```

Available locations for placing the invariant:
{chr(10).join(locations)}

Format:
assert(<predicate>); // Line <label>

Where:
- <predicate> is a valid boolean C expression
- <label> is one of the available location labels ({available_labels})
- Don't include explanations, just the assert statement

Example format:
assert(x >= 0 && y < 100); // Line A
"""
    return "You understand C programs well and can generate strong loop invariants for program verification.", user_msg
    

def parse_response(response_content: str, name_to_line: dict, sorted_lines: list):
    """Parse model response to extract predicate and line number."""
    if not response_content:
        return None, None
    
    # Find assert statements - handle nested parentheses
    assert_pos = response_content.find('assert(')
    if assert_pos == -1:
        return None, None
    
    # Find the matching closing parenthesis for assert( by tracking paren depth
    paren_count = 0
    start_pos = assert_pos + 7  # position after "assert(" (7 chars: a-s-s-e-r-t-()
    end_pos = None
    
    for i in range(start_pos, len(response_content)):
        if response_content[i] == '(':
            paren_count += 1
        elif response_content[i] == ')':
            if paren_count == 0:
                # This is the closing paren for assert(
                end_pos = i
                break
            else:
                paren_count -= 1
    
    if end_pos is None:
        return None, None
    
    # Extract predicate
    predicate = response_content[start_pos:end_pos].strip()
    
    # Look for comment with line label after );
    rest = response_content[end_pos:]
    comment_patterns = [
        r'\);\s*//\s*Line\s+([A-Z])',
        r'\);\s*//\s*([A-Z])',
        r'\);\s*/\*\s*Line\s+([A-Z])\s*\*/',
        r'\);\s*//\s*([a-z])',
    ]
    
    for pattern in comment_patterns:
        match = re.search(pattern, rest, re.IGNORECASE)
        if match:
            label = match.group(1).upper()
            if label in name_to_line:
                return predicate, name_to_line[label]
    
    # # Fallback: if predicate extracted but no label, use first line
    # if sorted_lines:
    #     return predicate, sorted_lines[0]
    
    return None, None