import os
from pathlib import Path
import json
from src.utils.rewriter import Rewriter
from src.utils.program import Program
from tqdm import tqdm
PATCH = ('void assert(int cond) { if (!(cond)) { ERROR : { reach_error(); abort(); } } }\n'
         'void assume(int cond) { if (!cond) { abort(); } }\n')

def clean_and_save_programs():
    input_dir = Path("dataset/training/Programs")
    output_dir = Path("dataset/training/clean")
    output_dir.mkdir(parents=True, exist_ok=True)
    no_assertions = {}
    for file_path in tqdm(input_dir.iterdir()):
        if file_path.is_file() and file_path.suffix == ".c":
            # Apply Rewriter with rewrite=True to the file
            r = Rewriter(file_path, rewrite=True)
            program = Program(r.lines_to_verify, r.replacement)
            if len(program.assertions) == 0:
                no_assertions[file_path.name] = True
                continue
            target_assert = program.assertions[0] # assuming there is only one assertion in the program
            program_str= program.get_program_with_assertion(predicate=target_assert, 
                                                         assumptions=[],
                                                         assertion_points={},
                                                         forGPT=False)
            # Write to the new location in output_dir
            cleaned_file_path = output_dir / file_path.name
            with open(cleaned_file_path, "w") as f:
                f.write(program_str)
                
        with open(output_dir / "no_assertions.json", "w") as f:
            json.dump(list(no_assertions.keys()), f)
if __name__ == "__main__":
    clean_and_save_programs()
