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
    
def load_json(file_path: Path) -> List[Dict]:
    """Load results from JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File {file_path} does not exist")
    with open(file_path, 'r') as f:
        data = json.load(f)
        if len(data) == 0:
            raise ValueError(f"JSON file {file_path} is empty")
        return data
    
    
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



def parse_uautomizer_output(output: str) -> str:
    import re
    result_pattern = r'Result:\s*\n(ERROR|TRUE|FALSE|UNKNOWN)(?::\s*(.+))?'
    match = re.search(result_pattern, output, re.MULTILINE)
    
    if match:
        decision = match.group(1)
        reason = match.group(2).strip() if match.group(2) else ""
        return decision, reason
    return "ERROR", "Unable to parse UAutomizer output."