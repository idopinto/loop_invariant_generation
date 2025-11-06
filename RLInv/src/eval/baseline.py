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
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from tqdm import tqdm
# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.plain_verifier import run_uautomizer
from src.utils.task import Task


def get_uautomizer_version(uautomizer_path: str) -> Dict[str, str]:
    """Get UAutomizer version using both --ultversion and --version flags."""
    versions = {}
    
    # Try --ultversion first
    try:
        result = subprocess.run(
            [sys.executable, uautomizer_path, '--ultversion'],
            capture_output=True,
            text=True,
            timeout=30
        )
        # Check both stdout and stderr (version info might be in either)
        output = (result.stdout + result.stderr).strip()
        if output:
            # Extract just the version line if multiple lines present
            lines = output.split('\n')
            # Look for line starting with "Version is"
            for line in lines:
                if 'Version is' in line:
                    versions['ultversion'] = line.strip()
                    break
            else:
                # If no "Version is" line, use first non-empty line
                versions['ultversion'] = lines[0] if lines else output
        else:
            versions['ultversion'] = "unknown"
    except Exception as e:
        versions['ultversion'] = f"unknown ({str(e)})"
    
    # Try --version
    try:
        result = subprocess.run(
            [sys.executable, uautomizer_path, '--version'],
            capture_output=True,
            text=True,
            timeout=30
        )
        # Check both stdout and stderr (version info might be in either)
        output = (result.stdout + result.stderr).strip()
        if output:
            # Usually just a commit hash or version string
            versions['version'] = output.split('\n')[0].strip()
        else:
            versions['version'] = "unknown"
    except Exception as e:
        versions['version'] = f"unknown ({str(e)})"
    
    return versions

def get_system_info() -> Dict[str, str]:
    """Get system hardware information."""
    try:
        # Get CPU info - matters for timing reproducibility
        cpu_info = "unknown"
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('model name'):
                        cpu_info = line.split(':')[1].strip()
                        break
        except (FileNotFoundError, PermissionError):
            pass
        
        # Get SLURM node name if available
        slurm_node = os.environ.get('SLURM_NODELIST') or os.environ.get('SLURMD_NODENAME')
        
        system_info = {
            "architecture": platform.machine(),
            "cpu": cpu_info,
            "python_version": platform.python_version()
        }
        
        if slurm_node:
            system_info["slurm_node"] = slurm_node
        
        return system_info
    except Exception:
        return {
            "architecture": platform.machine(),
            "cpu": "unknown",
            "python_version": platform.python_version()
        }

def detect_slurm_resources() -> Dict[str, int]:
    """Detect SLURM resource allocation from environment variables."""
    resources = {}
    
    # SLURM CPUs
    if 'SLURM_CPUS_PER_TASK' in os.environ:
        try:
            resources['slurm_cpus_per_task'] = int(os.environ['SLURM_CPUS_PER_TASK'])
        except (ValueError, TypeError):
            pass
    elif 'SLURM_CPUS_ON_NODE' in os.environ:
        try:
            resources['slurm_cpus_per_task'] = int(os.environ['SLURM_CPUS_ON_NODE'])
        except (ValueError, TypeError):
            pass
    
    # SLURM Memory (can be in MB or GB, need to parse)
    if 'SLURM_MEM_PER_NODE' in os.environ:
        try:
            mem_mb = int(os.environ['SLURM_MEM_PER_NODE'])
            resources['slurm_memory_gb'] = mem_mb // 1024  # Convert MB to GB
        except (ValueError, TypeError):
            pass
    elif 'SLURM_MEM_PER_CPU' in os.environ:
        try:
            mem_mb_per_cpu = int(os.environ['SLURM_MEM_PER_CPU'])
            cpus = resources.get('slurm_cpus_per_task', 1)
            resources['slurm_memory_gb'] = (mem_mb_per_cpu * cpus) // 1024
        except (ValueError, TypeError):
            pass
    
    # SLURM Time limit (format: "HH:MM:SS" or seconds as string, or "UNLIMITED")
    if 'SLURM_TIME_LIMIT' in os.environ:
        time_str = os.environ['SLURM_TIME_LIMIT']
        try:
            # Skip if unlimited
            if time_str.upper() == 'UNLIMITED':
                pass
            # Try parsing as seconds first
            elif ':' not in time_str:
                seconds = int(time_str)
                if seconds > 0:
                    resources['slurm_timeout_hours'] = seconds // 3600
            else:
                # Parse HH:MM:SS format
                parts = time_str.split(':')
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = int(parts[2])
                    total_hours = hours + minutes / 60 + seconds / 3600
                    if total_hours > 0:
                        resources['slurm_timeout_hours'] = int(total_hours) if total_hours < 1 else round(total_hours, 1)
        except (ValueError, TypeError, IndexError):
            pass
    
    return resources

def detect_java_heap_size(uautomizer_path: str) -> Optional[int]:
    """Detect Java heap size from UAutomizer script or environment."""
    # Check _JAVA_OPTIONS environment variable first
    if '_JAVA_OPTIONS' in os.environ:
        java_opts = os.environ['_JAVA_OPTIONS']
        # Look for -Xmx pattern (e.g., -Xmx15G, -Xmx12288M)
        match = re.search(r'-Xmx(\d+)([GMK])', java_opts)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            if unit == 'G':
                return value
            elif unit == 'M':
                return value // 1024  # Convert MB to GB
            elif unit == 'K':
                return value // (1024 * 1024)
    
    # Try to parse from Ultimate.py file
    try:
        uautomizer_file = Path(uautomizer_path)
        if uautomizer_file.exists():
            with open(uautomizer_file, 'r') as f:
                content = f.read()
                # Look for -Xmx pattern in the script
                match = re.search(r'-Xmx(\d+)([GMK])', content)
                if match:
                    value = int(match.group(1))
                    unit = match.group(2)
                    if unit == 'G':
                        return value
                    elif unit == 'M':
                        return value // 1024
                    elif unit == 'K':
                        return value // (1024 * 1024)
    except Exception:
        pass
    
    return None

def detect_z3_memory_limit(uautomizer_path: str) -> Optional[int]:
    """Detect Z3 memory limit from UAutomizer configuration."""
    # Z3 memory limit can be set in multiple places:
    # 1. Ultimate.py script (as -memory: parameter)
    # 2. Config XML files (in tools/uautomizer/config/)
    # 3. Environment variables
    
    # First, check Ultimate.py script
    try:
        uautomizer_file = Path(uautomizer_path)
        if uautomizer_file.exists():
            with open(uautomizer_file, 'r') as f:
                content = f.read()
                # Look for -memory: pattern (e.g., -memory:12288)
                match = re.search(r'-memory:(\d+)', content)
                if match:
                    return int(match.group(1))
    except Exception:
        pass
    
    # Check config XML files
    try:
        uautomizer_dir = Path(uautomizer_path).parent
        config_dir = uautomizer_dir / "config"
        if config_dir.exists():
            for config_file in config_dir.glob("*.xml"):
                try:
                    with open(config_file, 'r') as f:
                        content = f.read()
                        # Look for memory settings in XML (could be various formats)
                        # Common patterns: memory="12288", -memory:12288, memory:12288
                        matches = re.findall(r'(?:memory=|memory:|-memory:)"?(\d+)"?', content, re.IGNORECASE)
                        for match in matches:
                            mem_val = int(match)
                            # Z3 memory is typically in MB, values like 2024, 12288 are common
                            if mem_val >= 1000:  # Reasonable Z3 memory limit (at least 1GB)
                                return mem_val
                except Exception:
                    continue
    except Exception:
        pass
    
    return None

def get_runtime_configuration(uautomizer_path: str) -> Dict[str, Any]:
    """Get runtime configuration values dynamically."""
    config = {}
    
    # Detect SLURM resources
    slurm_resources = detect_slurm_resources()
    config.update(slurm_resources)
    
    # Detect Java heap size
    java_heap = detect_java_heap_size(uautomizer_path)
    if java_heap is not None:
        config['uautomizer_java_heap_max_gb'] = java_heap
    
    # Detect Z3 memory limit
    z3_memory = detect_z3_memory_limit(uautomizer_path)
    if z3_memory is not None:
        config['z3_memory_limit_mb'] = z3_memory
    
    return config

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
        default=600,
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
    uautomizer_versions = get_uautomizer_version(uautomizer_path)
    system_info = get_system_info()
    
    # Detect runtime configuration dynamically
    detected_config = get_runtime_configuration(uautomizer_path)
    
    # Build configuration: use detected values only
    configuration = {
        "per_instance_timeout_seconds": args.timeout,
        "uautomizer_java_heap_max_gb": detected_config.get('uautomizer_java_heap_max_gb'),
        "slurm_cpus_per_task": detected_config.get('slurm_cpus_per_task'),
        "slurm_memory_gb": detected_config.get('slurm_memory_gb')
    }
    
    print(f"UAutomizer --ultversion: {uautomizer_versions.get('ultversion', 'unknown')}")
    print(f"UAutomizer --version: {uautomizer_versions.get('version', 'unknown')}")
    print(f"System info: {system_info}")
    print(f"Detected configuration: {detected_config}")
    
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
    results_file = output_dir / "baseline_timing.json"
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
        "uautomizer_versions": uautomizer_versions,
        "system_info": system_info,
        "configuration": configuration,
        "total_problems": len(problems),
        "total_time": total_time,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "evaluation_folder": str(evaluation_dir),
        "timeout_seconds": args.timeout
    }
    
    # Save metadata separately
    metadata_file = output_dir / "baseline_metadata.json"
    try:
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"\nMetadata saved successfully to: {metadata_file}")
    except Exception as e:
        print(f"\nERROR: Failed to save metadata to {metadata_file}: {e}")
        raise
    
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
