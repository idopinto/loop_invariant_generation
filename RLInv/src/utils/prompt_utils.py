from copy import copy
from src.utils.program import Program


def build_prompt(formatted_program: str, assertion_points: dict, 
                     sorted_lines: list):
    """Build system and user messages for the prompt."""
    
    system_msg = "You understand C programs well and can generate strong loop invariants for program verification."
    locations = [f"  Line {ln} ({', '.join([a.name for a in assertion_points[ln]])})" 
                     for ln in sorted_lines]
    available_lines = ', '.join([str(ln) for ln in sorted_lines])
    user_msg = f"""Given the following C program, generate a loop invariant that implies the target property and its location in the program.
```c
{formatted_program}
```

Available locations for placing the invariant:
{chr(10).join(locations)}

Output Format:
assert(<predicate>); // Line <line_number>

Where:
- <predicate> is a valid boolean C expression
- <line_number> is one of the available line numbers ({available_lines})
"""
    return system_msg, user_msg


def format_program_with_labels(program: Program, assertion_points: dict) -> str:
    """Format program with location line numbers and target assertion."""
    lines = copy(program.lines)
    for i, line in enumerate(lines):
        if line in program.replacement_for_GPT:
            lines[i] = program.replacement_for_GPT[line]
    for lemma in program.lemmas:
        lines[lemma.line_number] += f"\nassume({lemma.content});"
    for line_num in sorted(assertion_points.keys()):
        if line_num < len(lines):
            lines[line_num] += f"\n// Line {line_num}"
    if program.assertions:
        target = program.assertions[0]
        if target.line_number < len(lines):
            lines[target.line_number] += f"\nassert({target.content}); // Target property"
    return "\n".join(lines)