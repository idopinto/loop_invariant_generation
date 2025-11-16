from pathlib import Path
# # Add the project root to Python path for imports
# project_root = Path(__file__).parent.parent.parent
# sys.path.insert(0, str(project_root))
# sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.utils.utils import load_yaml_file
from src.utils.paths import PROPERTIES_DIR

class Task:
    def __init__(self, directory: Path, filename: str, property_kind: str = "unreach"):
        self.yml_file = directory / f"{filename}.yml"
        self.source_code_path = directory / f"{filename}.c"

        self.data = load_yaml_file(self.yml_file)
        self.property_kind = property_kind
        assert(property_kind in ["unreach"])
        properties = self.data["properties"]
        self.property_path = None
        self.answer = None
        for p in properties:
            if property_kind == "unreach" and p["property_file"] == "unreach-call.prp":
                self.property_path = PROPERTIES_DIR / p["property_file"]
                self.answer = p["expected_verdict"]
                break
            
        if not (self.property_path is not None and self.answer is not None):
            self.property_path = PROPERTIES_DIR / "unreach-call.prp"
            self.answer = "unknown"
        assert(self.data["options"]["language"] == "C")
        if "32" in self.data['options']['data_model']:
            self.arch = "32bit"
        elif "64" in self.data['options']['data_model']:
            self.arch = "64bit"
        else:
            raise ValueError(f"Unknown architecture: {self.data['options']['data_model']}")

    def __repr__(self):
        repr_str = f"------------------------- TASK ({self.yml_file.stem}) ------------------------------\n"
        repr_str += f"  YAML file path: {self.yml_file}\n"
        repr_str += f"  Source code path: {self.source_code_path}\n"
        repr_str += f"  Property path: {self.property_path}\n"
        repr_str += f"  Property kind: {self.property_kind}\n"
        repr_str += f"  Expected Answer: {self.answer}\n"
        repr_str += f"  Architecture: {self.arch}\n"
        repr_str +=  "  Data:\n"
        for key, value in self.data.items():
            repr_str += f"    {key}: {value}\n"
        repr_str += "--------------------------------------------------------------------------------\n"
        return repr_str
    # def dump(self):
    #     print(self.data)