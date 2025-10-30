from typing import Dict
import sys
import re
from pathlib import Path

# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.utils.utils import run_subprocess_and_get_output
from configs import global_configurations as GC


class Rewriter:
    """
    Processes C code by removing comments, formatting, and replacing verification functions.
    
    Transforms C code with verification annotations into clean, formatted code suitable
    for analysis by replacing __VERIFIER_* functions with standard equivalents.
    """
    def __init__(self, filename: Path, rewrite=True, handle_reach_error=False):
        """Initialize rewriter with C code from file."""
        self.code = filename.read_text().strip() # type: ignore
        self.new_code = self.code

        if rewrite:
            # Process code: remove comments, format, and replace verification functions
            self.remove_comments()
            self.remove_re_pattern(r'__attribute__\s*\(\(.*?\)\)')

            # Remove verification functions
            self.remove_function("void reach_error")
            self.remove_function("void __VERIFIER_assert")
            self.remove_function("void assert")
            self.remove_function("void assume_abort_if_not")
            self.remove_function("void assume")
            self.remove_externs()

            # Replace verification functions with standard equivalents
            self.new_code = self.new_code.replace("__VERIFIER_assert", "assert")
            self.new_code = self.new_code.replace("assume_abort_if_not", "assume")
            self.clang_format()
            self.remove_empty_lines()
            self.has_reach_error = False
            if handle_reach_error:
                self.replace_reach_error_with_assertion()

            self.lines_to_verify = self.new_code.split("\n")

            # Replace nondeterministic functions with random values
            self.remove_verifier_nondet()

            self.lines_for_gpt = self.new_code.split("\n")

            # Track replacements for verification
            self.replacement: Dict[str, str] = {}
            assert(len(self.lines_for_gpt) == len(self.lines_to_verify))
            for i in range(len(self.lines_to_verify)):
                if self.lines_to_verify[i] != self.lines_for_gpt[i]:
                    self.replacement[self.lines_to_verify[i]] = self.lines_for_gpt[i]

    def find_all_loops(self):
        """Count total number of loops in the code using clang AST."""
        tmp_file = Path("tmp.c")
        tmp_file.write_text(self.new_code)
        command = "clang -cc1 -ast-dump tmp.c"
        output, err = run_subprocess_and_get_output(command)
        tmp_file.unlink()
        num_loops = output.count("ForStmt") + output.count("WhileStmt") + \
            output.count("DoStmt")
        return num_loops

    def remove_re_pattern(self, pattern):
        """Remove text matching the given regex pattern."""
        self.new_code = re.sub(pattern, '', self.new_code)

    def remove_function(self, func_name: str):
        """Remove function definition from code by finding matching braces."""
        c_code = self.new_code
        function_index = c_code.find(func_name)

        if function_index == -1:
            return None
        open_brackets = 0
        close_brackets = 0

        # Find the block that defines the function by matching braces
        for i in range(function_index, len(c_code)):
            if c_code[i] == '{':
                open_brackets += 1
            elif c_code[i] == '}':
                close_brackets += 1

                if open_brackets == close_brackets:
                    break
        self.new_code = c_code[: function_index] + c_code[i + 1: ]
        return


    def nondet_type(self, type_str : str):
        """Convert nondet type to C cast expression."""
        if type_str == "uchar":
            return "(unsigned char)"
        elif type_str == "char":
            return "(signed char)"
        elif type_str == "uint":
            return "(unsigned int)"
        else:
            return f"({type_str})"

    def get_tokens_with_verifier_nondet(self, input_string):
        """Extract all __VERIFIER_nondet_* tokens from input string."""
        pattern = r'\b__VERIFIER_nondet_\w+\b'
        tokens = set(re.findall(pattern, input_string))
        return tokens

    def remove_verifier_nondet(self):
        """Replace __VERIFIER_nondet_* functions with random value casts."""
        tokens = self.get_tokens_with_verifier_nondet(self.new_code)
        for token in tokens:
            pattern = token + "()"
            replacement = self.nondet_type(token.split("__VERIFIER_nondet_")[1]) + " rand()"
            self.new_code = self.new_code.replace(pattern, replacement)

    def remove_externs(self):
        """Remove extern declarations and __extension__ prefixes."""
        pattern = r'\bextern\s+.*?;'
        functions = re.findall(pattern, self.new_code, re.MULTILINE | re.DOTALL)
        for function in functions:
            self.new_code = self.new_code.replace(function, "")
        self.new_code = self.new_code.strip()
        lines = self.new_code.split("\n")
        new_lines = []
        for line in lines:
            if line.strip()[:13] == "__extension__":
                new_lines.append(line[13:])
            else:
                new_lines.append(line)
        self.new_code = "\n".join(new_lines)

    def clang_format(self):
        """Format code using clang-format with custom style configuration."""
        tmp_file = Path("tmp.c")
        with tmp_file.open('w') as out_file:
            out_file.write(self.new_code)
        command = f"clang-format-15 --style=file:{GC.PATH_TO_CLANG_FORMAT} ./tmp.c"
        output, err = run_subprocess_and_get_output(command)
        tmp_file.unlink()
        self.new_code = output

    def remove_empty_lines(self):
        """Remove empty lines from the code."""
        lines = self.new_code.split("\n")
        new_lines = []
        for line in lines:
            if line == "":
                continue
            else:
                new_lines.append(line)
        self.new_code = "\n".join(new_lines)


    def remove_comments(self):
        """Remove C comments using gcc preprocessor and filter output."""
        self.clang_format()
        tmp_file = Path("tmp.c")
        tmp_file.write_text(self.new_code)
        # Remove comments using gcc preprocessor
        command = "gcc -fpreprocessed -dD -E tmp.c"
        output, err = run_subprocess_and_get_output(command)
        tmp_file.unlink()
        self.new_code = output

        # Filter out preprocessor directives and comments
        lines = self.new_code.split("\n")
        new_lines = []
        for line in lines:
            if line.strip()[:2] == "//":
                continue
            elif line.strip()[:1] == "#":
                continue
            else:
                new_lines.append(line)
        self.new_code = "\n".join(new_lines)


    def replace_reach_error_with_assertion(self):
        """Replace reach_error() calls with assert(!condition) statements."""
        c_code = self.new_code
        indices_object = re.finditer(pattern='reach_error', string=c_code)
        indices = [index.start() for index in indices_object]
        indices.reverse()

        for function_index in indices:
            self.has_reach_error = True
            assertion_start = None
            assertion_end = None
            block_end = None
            # Find the block that defines the function
            for i in range(function_index, 0, -1):
                if c_code[i] == ')' and assertion_end is None:
                    assertion_end = i
                if c_code[i:i + 3] == "if ":
                    assert(assertion_start is None and assertion_end is not None)
                    assertion_start = i + 3
                    break

            for i in range(function_index, len(c_code)):
                if c_code[i] == '}':
                    block_end = i
            condition = c_code[assertion_start: assertion_end + 1]
            condition = f"assert(!{condition});"
            c_code = c_code[:assertion_start - 3] + condition + c_code[block_end + 1:]

        self.new_code = c_code