from asyncio import Task
import datetime
import yaml
import subprocess
from pathlib import Path
from typing import List, Dict, Optional 
import json


def _sanitize(name: str) -> str:
    return name.replace("/", "_").replace(" ", "_")

def save_as_json(content: dict, save_path: Path) -> None:
    with open(save_path, 'w') as f:
        json.dump(content, f, indent=2)
    print(f"\nResults saved to:\n\t {save_path}")
    
def load_json(file_path: Path) -> List[Dict]:
    """Load results from JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)
    
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

def load_dataset(dataset_path: Path, property_kind: str = "unreach", limit: int = None, prefix: Optional[str] = None, suffix: Optional[str] = None) -> List[Task]:
    """Load dataset from YAML files."""
    from src.utils.task import Task  # Import here to avoid circular import
    tasks = []
    print(f"Loading dataset from: {dataset_path}")
    for yml_file in dataset_path.glob("*.yml"):
        # print(yml_file)s
        if limit is not None and limit != -1 and len(tasks) >= limit:
            break
        if prefix is not None and not yml_file.stem.startswith(prefix):
            continue
        if suffix is not None and not yml_file.stem.endswith(suffix):
            continue
        task = Task(yml_file_path=yml_file, property_kind=property_kind)
        tasks.append(task)
    return tasks

# def load_baseline_results(baseline_file: Path) -> List[Dict]:
#     """Load baseline results from JSON file. If the file does not exist, return an empty list."""
#     if not baseline_file.exists():
#         print(f"Warning: Baseline file not found at {baseline_file}, using default timeouts")
#         return []
#     try:
#         with open(baseline_file, 'r') as f:
#             return json.load(f)
#     except Exception as e:
#         print(f"Warning: Failed to load baseline results from {baseline_file}: {e}, using default timeouts")
#         return []
