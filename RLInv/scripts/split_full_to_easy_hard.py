#!/usr/bin/env python3
"""
Split full dataset into easy and hard based on baseline timing.
Easy: timing <= 30 seconds
Hard: timing > 30 seconds
"""

import json
import shutil
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.utils import load_yaml_file

# Paths
full_dir = Path("dataset/evaluation/full")
easy_dir = Path("dataset/evaluation/easy")
hard_dir = Path("dataset/evaluation/hard")

# Create output directories
easy_dir.mkdir(parents=True, exist_ok=True)
hard_dir.mkdir(parents=True, exist_ok=True)
(easy_dir / "c").mkdir(exist_ok=True)
(easy_dir / "yml").mkdir(exist_ok=True)
(hard_dir / "c").mkdir(exist_ok=True)
(hard_dir / "yml").mkdir(exist_ok=True)

# Load baseline timing results
timing_file = full_dir / "baseline_timing.json"
with open(timing_file, 'r') as f:
    results = json.load(f)

# Create lookup: base_filename -> timing
timing_lookup = {r["base_filename"]: r["baseline_timing"] for r in results}

# Split by timing
easy_files = []
hard_files = []

for base_filename, timing in timing_lookup.items():
    if timing <= 30:
        easy_files.append(base_filename)
    else:
        hard_files.append(base_filename)

# Copy files
def copy_files(base_filenames, dest_dir):
    for base_filename in base_filenames:
        src_yml = full_dir / "yml" / f"{base_filename}.yml"
        if not src_yml.exists():
            print(f"Warning: YML file not found: {src_yml}")
            continue
        
        # Get actual C filename from yml
        try:
            yml_data = load_yaml_file(src_yml)
            c_filename = yml_data.get("input_files", f"{base_filename}.c")
        except Exception:
            c_filename = f"{base_filename}.c"
        
        src_c = full_dir / "c" / c_filename
        dst_c = dest_dir / "c" / c_filename
        dst_yml = dest_dir / "yml" / f"{base_filename}.yml"
        
        if src_c.exists():
            shutil.copy2(src_c, dst_c)
        else:
            print(f"Warning: C file not found: {src_c}")
        
        shutil.copy2(src_yml, dst_yml)

copy_files(easy_files, easy_dir)
copy_files(hard_files, hard_dir)

print(f"Easy: {len(easy_files)} problems (timing <= 30s)")
print(f"Hard: {len(hard_files)} problems (timing > 30s)")

