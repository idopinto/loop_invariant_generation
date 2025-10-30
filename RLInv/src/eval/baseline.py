#!/usr/bin/env python3
"""
Baseline script for running UAutomizer on evaluation problems.

This script processes a folder containing yml and c files, runs UAutomizer
on each problem, measures timing, and outputs results in JSON format.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List
from tqdm import tqdm
# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.plain_verifier import run_uautomizer
from src.utils.task import Task


def get_uautomizer_version(uautomizer_path: str) -> str:
    """Get UAutomizer version."""
    try:
        result = subprocess.run(
            [uautomizer_path, '--version'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return "unknown"
    except Exception:
        return "unknown"

def get_system_info() -> Dict[str, str]:
    """Get system hardware information."""
    try:
        # Get CPU info
        cpu_info = "unknown"
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('model name'):
                        cpu_info = line.split(':')[1].strip()
                        break
        except (FileNotFoundError, PermissionError):
            pass
        
        # Get memory info
        memory_info = "unknown"
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal'):
                        memory_info = line.split(':')[1].strip()
                        break
        except (FileNotFoundError, PermissionError):
            pass
        
        return {
            "os": f"{platform.system()} {platform.release()}",
            "architecture": platform.machine(),
            "cpu": cpu_info,
            "memory": memory_info,
            "python_version": platform.python_version()
        }
    except Exception:
        return {
            "os": "unknown",
            "architecture": "unknown", 
            "cpu": "unknown",
            "memory": "unknown",
            "python_version": platform.python_version()
        }

def find_problem_files(evaluation_dir: Path) -> List[Path]:
    """
    Find all yml files in the evaluation directory.
    
    Returns:
        List of yml file paths for each problem
    """
    problems = []
    
    # Look for yml files
    yml_dir = evaluation_dir / "yml"
    
    if not yml_dir.exists():
        raise ValueError(f"YML directory not found: {yml_dir}")
    
    for yml_file in yml_dir.glob("*.yml"):
        problems.append(yml_file)
    
    return problems

def process_problem(
    yml_file: Path,
    uautomizer_path: str,
    properties_dir: Path,
    timeout_seconds: int = 300
) -> Dict:
    """Process a single problem and return results."""
    
    try:
        # Create Task object using existing code
        # Pass the full path so Task can infer the correct c_dir
        task = Task(yml_file, property_kind="unreach")
        
        # Get base filename
        base_filename = yml_file.stem
        
        # print(f"Processing: {base_filename}")
        # print(f"  C file: {task.source_code_path}")
        # print(f"  Property file: {task.property_path}")
        # print(f"  Architecture: {task.arch}")
        # print(f"  Expected answer: {task.answer}")
        
        # Run UAutomizer without saving log files
        report = run_uautomizer(
            uautomizer_path=uautomizer_path,
            c_file_path=str(task.source_code_path),
            property_file_path=str(task.property_path),
            reports_dir=Path("/tmp"),  # Use temp directory, we won't keep these files
            arch=task.arch,
            timeout_seconds=timeout_seconds
        )
        
        # Convert decision to string
        decision_str = report.decision.name if report.decision else "Unknown"
        return {
            "base_filename": base_filename,
            "decision": decision_str,
            "baseline_timing": report.time_taken,
            "architecture": task.arch,
            "property_file": Path(task.property_path).name,  # Only filename, not full path
            "expected_answer": task.answer
        }
        
    except Exception as e:
        print(f"Error creating Task for {yml_file}: {e}")
        return {
            "base_filename": yml_file.stem,
            "decision": "Error",
            "baseline_timing": 0.0,
            "error_message": str(e)
        }


def main():
    parser = argparse.ArgumentParser(
        description="Run UAutomizer baseline on evaluation problems"
    )
    parser.add_argument(
        "evaluation_folder",
        help="Path to evaluation folder (e.g., evaluation/easy)"
    )
    parser.add_argument(
        "--uautomizer-path",
        default="/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/tools/uautomizer/Ultimate.py",
        help="Path to UAutomizer executable"
    )
    parser.add_argument(
        "--properties-dir",
        default="/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/dataset/properties",
        help="Path to properties directory"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for results and metadata (default: saves directly to evaluation directory)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds for each verification"
    )
    
    args = parser.parse_args()
    
    # Convert to Path objects
    evaluation_dir = Path(args.evaluation_folder)
    uautomizer_path = args.uautomizer_path
    properties_dir = Path(args.properties_dir)
    
    # Validate paths
    if not evaluation_dir.exists():
        print(f"Error: Evaluation directory not found: {evaluation_dir}")
        sys.exit(1)
    
    if not os.path.exists(uautomizer_path):
        print(f"Error: UAutomizer not found: {uautomizer_path}")
        sys.exit(1)
    
    if not properties_dir.exists():
        print(f"Error: Properties directory not found: {properties_dir}")
        sys.exit(1)
    
    # Use explicit output_dir if provided, otherwise save directly to evaluation directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
        evaluation_folder_name = evaluation_dir.name
        output_dir = output_dir / evaluation_folder_name
    else:
        output_dir = evaluation_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get metadata
    uautomizer_version = get_uautomizer_version(uautomizer_path)
    system_info = get_system_info()
    
    print(f"UAutomizer version: {uautomizer_version}")
    print(f"System info: {system_info}")
    
    # Find all problems
    try:
        problems = find_problem_files(evaluation_dir)
        print(f"Found {len(problems)} problems to process")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    if not problems:
        print("No problems found to process")
        sys.exit(1)
    
    # Process each problem
    results = []
    start_time = time.time()
    
    # Create results file and write initial empty array
    results_file = output_dir / "baseline_results.json"
    with open(results_file, 'w') as f:
        json.dump([], f)
    
    for i, yml_file in tqdm(enumerate(problems, 1), total=len(problems), desc="Processing problems"):
        # print(f"\n[{i}/{len(problems)}] Processing {yml_file.name}")
        
        try:
            result = process_problem(
                yml_file=yml_file,
                uautomizer_path=uautomizer_path,
                properties_dir=properties_dir,
                timeout_seconds=args.timeout
            )
            results.append(result)
            
            # print(f"  Result: {result['decision']}")
            # print(f"  Time: {result['baseline_timing']:.2f}s")
            
        except Exception as e:
            print(f"  Error processing {yml_file.name}: {e}")
            # Add error result
            error_result = {
                "base_filename": yml_file.stem,
                "decision": "Error",
                "baseline_timing": 0.0,
                "error_message": str(e)
            }
            results.append(error_result)
        
        # Write results incrementally after each problem
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
    
    total_time = time.time() - start_time
    
    # Create metadata
    metadata = {
        "uautomizer_version": uautomizer_version,
        "system_info": system_info,
        "configuration": {
            "per_instance_timeout_seconds": args.timeout,
            "z3_memory_limit_mb": 12288,
            "uautomizer_java_heap_max_gb": 15,
            "sv_comp_compliant": True,
            "slurm_cpus_per_task": 8,
            "slurm_memory_gb": 16,
            "slurm_timeout_hours": 2
        },
        "sv_comp_standards": {
            "memory_gb": 15,
            "cpu_cores": 8,
            "timeout_minutes": 15,
            "description": "Configuration updated to match SV-COMP 2023-2025 standards"
        },
        "total_problems": len(problems),
        "total_time": total_time,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "evaluation_folder": str(evaluation_dir),
        "timeout_seconds": args.timeout,
        "notes": "Configuration updated from original settings to SV-COMP standards. Z3 memory limits increased from 1-2GB to 12GB, timeout increased from 60s to 900s, SLURM resources updated to 8 cores and 16GB RAM."
    }
    
    # Save metadata separately
    metadata_file = output_dir / "baseline_metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print("\n=== Baseline Complete ===")
    print(f"Processed {len(problems)} problems in {total_time:.2f}s")
    print(f"Results saved to: {results_file}")
    print(f"Metadata saved to: {metadata_file}")
    
    # Summary statistics
    decisions = [r["decision"] for r in results]
    decision_counts = {}
    for decision in decisions:
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    
    print("\nDecision summary:")
    for decision, count in decision_counts.items():
        print(f"  {decision}: {count}")


if __name__ == "__main__":
    main()
