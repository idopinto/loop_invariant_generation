import datetime

import pycparser
import yaml
import argparse
import subprocess
import os
from os.path import join, basename, abspath
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="GPT4MC.")
    parser.add_argument("input", help="Path to the yaml file.")
    parser.add_argument("-v", "--verifier", type=str, default="esbmc",
                        choices=["uautomizer", "cbmc", "esbmc", "2ls", "seahorn", "all"],
                        help="Verifier uautomizer/cbmc/esbmc/2ls/seahorn/all.")
    parser.add_argument("--prop", type=str, default="reach", choices=["term", "reach"],
                        help="Property type term/reach.")
    parser.add_argument("--learn", action="store_true", help="Use GPT?")
    parser.add_argument("-w", "--working-dir", type=str, default="./data/", help="Working directory")
    parser.add_argument("--verbosity", type=int, default=1, help="Verbosity")
    parser.add_argument("--seed", type=int, default=1, help="Seed")
    parser.add_argument("--num-assertions", type=int, default=2, help="Number of assertions")
    parser.add_argument("--num-attempts", type=int, default=4, help="Number of attempts for GPT")
    parser.add_argument("--simulate", action="store_true", help="Simulate?")
    parser.add_argument("--no-repair", action="store_true", help="Does not perform refinement")
    parser.add_argument("--per-instance-timeout", type=int, default=900, help="Per-instance timeout")
    parser.add_argument("--model", type=str, default="gpt-4", choices=["gpt-4", "gpt-3.5-turbo"],
                        help="Model")

    args = parser.parse_args()
    print("-------------Arguments-------------------")
    for key, value in args.__dict__.items():
        print(f"{key}: {value}")
    print("-------------------------------------------------------------")
    return args


def load_yaml_file(file_path):
    try:
        with open(file_path, "r") as file:
            data = yaml.safe_load(file)
            return data
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' does not exist.")
        return None
    except yaml.YAMLError as e:
        print(f"Error: Failed to parse YAML file '{file_path}': {e}")
        return None


def run_subprocess(command, live_output: bool = True, timeout: int= 60):
    stdout = []
    stderr = []
    process = subprocess.Popen(
        f"timeout {timeout} " + command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,  # Line buffered (output line by line)
        shell=True  # Use shell to allow using command with pipes and redirections
    )

    # Loop to read and print the output line by line in real-time
    for line in process.stdout:
        if live_output:
            print(line, end='')
        stdout.append(line)

    # Make sure to capture any remaining output
    for line in process.stderr:
        if live_output:
            print(line, end='')
        stderr.append(line)

    # Wait for the process to finish
    process.wait()
    return stdout, stderr


def run_subprocess_and_get_output(command):
    p = subprocess.run(command.split(), capture_output=True)
    return p.stdout.decode('utf-8', errors='replace'), p.stderr.decode('utf-8', errors='replace')

import datetime

def create_working_dir(working_dir: Path, c_filename: Path, property_kind: str):
    # Create base directory without timestamp
    base_dir = working_dir / f"{c_filename.stem}_{property_kind}"
    
    # Create human-readable timestamp folder inside base directory
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_dir = base_dir / timestamp
    
    try:
        timestamped_dir.mkdir(parents=True, exist_ok=True)
        print(f"Timestamped directory created: {timestamped_dir.absolute()}")
        code_dir = timestamped_dir / "code"
        code_dir.mkdir(parents=True, exist_ok=True)
        print(f"Code directory created: {code_dir.absolute()}")
        return timestamped_dir.absolute(), code_dir.absolute()  # Return absolute paths
    except Exception as e:
        print(f"Unable to create working directory: {timestamped_dir.absolute()}")
        print(f"Error: {e}")
        exit(1)
        
class color:
   PURPLE = '\033[95m'
   CYAN = '\033[96m'
   DARKCYAN = '\033[36m'
   BLUE = '\033[94m'
   GREEN = '\033[92m'
   YELLOW = '\033[93m'
   RED = '\033[91m'
   BOLD = '\033[1m'
   UNDERLINE = '\033[4m'
   END = '\033[0m'

def bold(text : str) -> str:
   return color.BOLD + text + color.END

def red(text : str) -> str:
   return color.RED + text + color.END

def blue(text : str) -> str:
   return color.BLUE + text + color.END

def check_equivalence(c1, c2):
    # parse the statements into ASTs
    try:
        ast1 = pycparser.c_parser.CParser().parse("void main() {" + f"assert({c1});" + "}")
        ast2 = pycparser.c_parser.CParser().parse("void main() {" + f"assert({c2});" + "}")

        # Compare the ASTs recursively
        return compare_nodes(ast1, ast2)
    except:
        return False

def compare_nodes(node1, node2):
    # Check if both nodes are None
    if node1 is None and node2 is None:
        return True

    # Check if one node is None and the other is not
    if node1 is None or node2 is None:
        return False

    # Check if both nodes have the same class
    if type(node1) != type(node2):
        return False

    # Check if both nodes have the same attributes
    for attr in node1.attr_names:
        if getattr(node1, attr) != getattr(node2, attr):
            return False

    # Check if both nodes have the same number of children
    if len(node1.children()) != len(node2.children()):
        return False

    # Compare the children recursively
    for child1, child2 in zip(node1.children(), node2.children()):
        if not compare_nodes(child1[1], child2[1]):
            return False

    # If all checks passed, return True
    return True