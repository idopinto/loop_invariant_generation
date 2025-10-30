import sys
from pathlib import Path

# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.utils.utils import load_yaml_file

root_dir = project_root
properties_dir = root_dir / "dataset" / "properties"

class Task:
    def __init__(self, yml_file_path: Path, property_kind: str = "unreach"):
        
        # If yml_file_path is already a full path (has 'yml' directory in it), use it directly
        # Otherwise, treat it as filename and use hardcoded easy dirs (backward compatibility)
        yml_file_path = Path(yml_file_path)
        if "yml" in yml_file_path.parts or yml_file_path.is_absolute():
            # Full path provided (e.g., dataset/evaluation/hard/yml/file.yml)
            self.yml_file = yml_file_path
            # Infer c_dir from yml_file path: .../evaluation/<split>/yml -> .../evaluation/<split>/c
            c_dir = self.yml_file.parent.parent / "c"
        # else:
        #     # Filename only - this should not happen with current code, but handle gracefully
        #     # Default to easy for backward compatibility
        #     yml_dir = root_dir / "dataset" / "evaluation" / "easy" / "yml"
        #     c_dir = root_dir / "dataset" / "evaluation" / "easy" / "c"
        #     self.yml_file = yml_dir / yml_file_path
        
        self.data = load_yaml_file(self.yml_file)
        self.property_kind = property_kind
        assert(property_kind in ["unreach", "term"])

        self.source_code_path = c_dir / self.data["input_files"]
        properties = self.data["properties"]
        self.property_path = None
        self.answer = None
        for p in properties:
            if property_kind == "unreach" and p["property_file"] == "unreach-call.prp":
                self.property_path = properties_dir / p["property_file"]
                self.answer = p["expected_verdict"]
                break
            elif property_kind == "term" and p["property_file"] == "termination.prp":
                self.property_path = properties_dir / p["property_file"]
                self.answer = p["expected_verdict"]
                break
            
        if not (self.property_path is not None and self.answer is not None):
            self.property_path = properties_dir / "unreach-call.prp"
            self.answer = "unknown"
        assert(self.data["options"]["language"] == "C")
        if "32" in self.data["options"]["data_model"]:
            self.arch = "32bit"
        else:
            self.arch = "64bit"

    def __repr__(self):
        repr_str = f"------------------------- TASK ({self.yml_file.stem}) ------------------------------\n"
        repr_str += f"  YAML file path: {self.yml_file}\n"
        repr_str += f"  Source code path: {self.source_code_path}\n"
        repr_str += f"  Property path: {self.property_path}\n"
        repr_str += f"  Property kind: {self.property_kind}\n"
        repr_str += f"  Expected Answer: {self.answer}\n"
        repr_str += f"  Architecture: {self.arch}\n"
        repr_str += f"  Data:\n"
        for key, value in self.data.items():
            repr_str += f"    {key}: {value}\n"
        repr_str += "--------------------------------------------------------------------------------\n"
        return repr_str
    # def dump(self):
    #     print(self.data)