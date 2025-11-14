from asyncio import Task
import datetime
import yaml
import subprocess
from pathlib import Path
from typing import List, Dict, Optional 
import json


def write_file(file_path: Path, content: str) -> None:
    """Helper to write content to file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        f.write(content)

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

def parse_uautomizer_output(output: str) -> str:
    import re
    result_pattern = r'Result:\s*\n(ERROR|TRUE|FALSE|UNKNOWN)(?::\s*(.+))?'
    match = re.search(result_pattern, output, re.MULTILINE)
    
    if match:
        decision = match.group(1)
        reason = match.group(2).strip() if match.group(2) else ""
        return decision, reason
    return "ERROR", "Unable to parse UAutomizer output."