from pathlib import Path

# Single source of truth for project root
# This file is in src/utils/, so go up 2 levels to reach RLInv/
ROOT_DIR = Path(__file__).parent.parent.parent

# Common paths derived from root
DATASET_DIR = ROOT_DIR / "dataset"
EVALUATION_DATASET_DIR = DATASET_DIR / "evaluation"
TRAINING_DATASET_DIR = DATASET_DIR / "training"
PROPERTIES_DIR = DATASET_DIR / "properties"
TOOLS_DIR = ROOT_DIR / "tools"
EXPERIMENTS_DIR = ROOT_DIR / "experiments"

# UAutomizer paths
UAUTOMIZER_PATHS = {
    "23": TOOLS_DIR / "UAutomizer23" / "Ultimate.py",
    "24": TOOLS_DIR / "UAutomizer24" / "Ultimate.py",
    "25": TOOLS_DIR / "UAutomizer25" / "Ultimate.py",
    "26": TOOLS_DIR / "UAutomizer26" / "Ultimate.py",
}