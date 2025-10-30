#!/usr/bin/env python3
"""
Script to generate .yml files for every .c file in evaluation/easy or evaluation/hard directory.
Each .yml file contains verification configuration based on timing.json results.
"""

import argparse
import json
import os
import shutil
from pathlib import Path

def load_timing_results(timing_file_path):
    """Load timing results from JSON file and create a mapping of filename to result."""
    with open(timing_file_path, 'r') as f:
        timing_data = json.load(f)
    
    # Create a mapping from filename to result
    results_map = {}
    for entry in timing_data:
        filename = entry['file']
        result = entry['result']
        results_map[filename] = result
    
    return results_map

def create_yml_content(filename, expected_verdict):
    """Create YAML content for a given C file."""
    yml_content = f"""format_version: '2.0'
input_files: {filename}
options:
  data_model: ILP32
  language: C
properties:
- expected_verdict: {expected_verdict.lower()}
  property_file: ../properties/unreach-call.prp
"""
    return yml_content

def main():
    parser = argparse.ArgumentParser(
        description="Generate .yml files for .c files in evaluation directory"
    )
    parser.add_argument(
        "split",
        choices=["easy", "hard"],
        help="Data split: easy or hard"
    )
    
    args = parser.parse_args()
    
    # Define paths
    base_dir = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/dataset/evaluation")
    split_dir = base_dir / args.split
    timing_file = base_dir / "timing.json"
    
    # Create output directories
    c_dir = split_dir / "c"
    yml_dir = split_dir / "yml"
    
    # Create directories if they don't exist
    c_dir.mkdir(exist_ok=True)
    yml_dir.mkdir(exist_ok=True)
    
    # Load timing results
    print(f"Loading timing results from: {timing_file}")
    timing_results = load_timing_results(timing_file)
    
    # Get all .c files in split directory
    c_files = list(split_dir.glob("*.c"))
    print(f"Found {len(c_files)} .c files in {args.split} directory")
    
    processed_count = 0
    missing_results = []
    
    for c_file in c_files:
        filename = c_file.name
        
        # Check if we have timing results for this file
        if filename in timing_results:
            expected_verdict = timing_results[filename]
            
            # Create YAML content
            yml_content = create_yml_content(filename, expected_verdict)
            
            # Write YAML file
            yml_filename = filename.replace('.c', '.yml')
            yml_file_path = yml_dir / yml_filename
            
            with open(yml_file_path, 'w') as f:
                f.write(yml_content)
            
            # Move C file to c/ directory
            c_file_dest = c_dir / filename
            shutil.move(str(c_file), str(c_file_dest))
            
            processed_count += 1
            print(f"Processed: {filename} -> {yml_filename} (verdict: {expected_verdict})")
        else:
            missing_results.append(filename)
            print(f"Warning: No timing result found for {filename}")
    
    print(f"\nSummary:")
    print(f"- Successfully processed: {processed_count} files")
    print(f"- Files with missing timing results: {len(missing_results)}")
    
    if missing_results:
        print(f"- Missing files: {', '.join(missing_results)}")
    
    print(f"\nFiles organized:")
    print(f"- C files moved to: {c_dir}")
    print(f"- YAML files created in: {yml_dir}")

if __name__ == "__main__":
    main()
