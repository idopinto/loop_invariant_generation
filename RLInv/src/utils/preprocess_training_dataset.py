import json
import re
from pathlib import Path
from tqdm import tqdm
from src.utils.rewriter import Rewriter
from src.utils.program import Program
from src.utils.prompt_utils import build_prompt, format_program_with_labels
'''
Goal: Generate a training dataset for the SFT model from the InvBench training dataset.
Source format:
        
            "file_name": "program_name.c" (the code in Programs/),
            "invariants": [
                {
                    "line": 10,
                    "invariant": "i <= n"
                },
                {
                    "line": 11,
                    "invariant": "i % 2 == 0"
                }
                ]
        
Target format:
        {
        "system": "You understand C programs well and can generate strong loop invariants for program verification.",
        "prompt": "Given the following C program, produce ... Available locations ...",
        "response": "assert(k == n - i/2 && i <= n && i % 2 == 0); // Line 10"
        }
'''

def create_training_dataset_per_invariant(dataset_path: Path, limit: int = None):
    """
    Generate a training dataset for the SFT model from the InvBench training dataset.
    
    Args:
        dataset_path: Path to the dataset directory
        limit: Optional limit on the number of programs to process. If None, processes all programs.
    """
    program_dir = Path(dataset_path) / "Programs"
    invariants_file = Path(dataset_path) / "invariants.json"

    print(f"Loading invariants from: {invariants_file}")
    with open(invariants_file, "r") as f:
        invariants_data = json.load(f)
        
    data = []
    items_to_process = list(invariants_data.items())[:limit] if limit else invariants_data.items()
    for program_name, invariant_list in tqdm(items_to_process, desc="Processing programs"):
        c_program_path = Path(program_dir) / program_name

        try:
            
            
            for invariant in invariant_list:
                gt_invariant_line_number = invariant['line']
                r = Rewriter(c_program_path, gt_invariant_line_number=gt_invariant_line_number)
                # print(r.lines_to_verify)
                program = Program(r.lines_to_verify, r.replacement)
                formatted_program = format_program_with_labels(program, program.assertion_points)
                original_line_num = invariant['line']
                gt_for_gpt = r.gt_for_gpt
                if gt_for_gpt not in program.assertion_points:
                    print("Program: ", program_name)
                    print("Assertion points: ", program.assertion_points)
                    print(program)
                    print(f"GT for GPT is not a valid location: {gt_for_gpt}")
                    continue
                # assert(gt_for_gpt in program.assertion_points)

                system_msg, user_msg = build_prompt(formatted_program, program.assertion_points, sorted(program.assertion_points.keys()))

                data_point = {
                    "id": program_name.split(".")[0] + "_" + f"line_{str(original_line_num)}",
                    "system": system_msg,
                    "prompt": user_msg,
                    "response": f"assert({invariant['invariant']}); // Line {gt_for_gpt}"
                }
                data.append(data_point)
        except Exception as e:
            print(f"Error processing program {program_name}: {e}")
            continue
    # save data to jsonl 
    with open(dataset_path / "train_data.jsonl", "w") as f:
        for data_point in data:
            f.write(json.dumps(data_point) + "\n")
            
if __name__ == "__main__":
    create_training_dataset_per_invariant(Path("dataset/training"), limit=4)