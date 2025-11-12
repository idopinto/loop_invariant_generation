#!/usr/bin/env python3
"""
Baseline script for running UAutomizer on evaluation problems.

This script processes a folder containing yml and c files, runs UAutomizer
on each problem, measures timing, and outputs results in JSON format.
"""

import argparse
import csv
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Any
from tqdm import tqdm
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from src.utils.plain_verifier import run_uautomizer
from src.utils.task import Task
from src.utils.utils import load_yaml_file
from src.utils.baseline_utils import get_verifier_version, get_system_info, get_runtime_configuration, detect_z3_memory_limit, detect_slurm_resources, detect_java_heap_size
 
root_dir = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv")

verifier_executable_paths = {
    "uautomizer23": root_dir / "tools" / "UAutomizer23" / "Ultimate.py",
    "uautomizer24": root_dir / "tools" / "UAutomizer24" / "Ultimate.py",
    "uautomizer25": root_dir / "tools" / "UAutomizer25" / "Ultimate.py",
    "uautomizer26": root_dir / "tools" / "UAutomizer26" / "Ultimate.py"
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
    uautomizer_path: Path,
    timeout_seconds: int = 300
) -> Dict[str, Any]:
    """Process a single problem and return results."""
    
    try:
        task = Task(yml_file, property_kind="unreach")
        
        report = run_uautomizer(
            uautomizer_path=uautomizer_path,
            program_path=str(task.source_code_path),
            property_file_path=str(task.property_path),
            reports_dir=Path("/tmp"),
            arch=task.arch,
            timeout_seconds=timeout_seconds
        )
        
        return {
            "file": yml_file.stem,
            "time": report.time_taken,
            "result": report.decision
        }
    except Exception as e:
        error_msg = str(e)
        print(f"Error processing {yml_file}: {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "file": yml_file.stem,
            "time": 0.0,
            "result": "ERROR",
            "error_message": error_msg
        }


def main():
    parser = argparse.ArgumentParser(
        description="Run UAutomizer baseline on evaluation problems"
    )
    parser.add_argument(
        "evaluation_folder",
        help="Path to evaluation folder (e.g., evaluation/full)"
    )
    parser.add_argument(
        "--uautomizer_version",
        default="uautomizer23",
        help="UAutomizer version (e.g., uautomizer23, uautomizer24, uautomizer25, uautomizer26)"
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
    parser.add_argument(
        "--do-split",
        action="store_true",
        help="Split full dataset into easy, hard, and unknowns after processing (only works when evaluation folder is 'full')"
    )
    
    args = parser.parse_args()
    
    # Convert to Path objects
    evaluation_dir = Path(args.evaluation_folder)
    verifier_executable_path = verifier_executable_paths[args.uautomizer_version]
    
    # Validate paths
    if not evaluation_dir.exists():
        print(f"Error: Evaluation directory not found: {evaluation_dir}")
        sys.exit(1)
    
    if not os.path.exists(verifier_executable_path):
        print(f"Error: UAutomizer not found: {verifier_executable_path}")
        sys.exit(1)
    
    # Extract version number from uautomizer_version (e.g., "uautomizer23" -> "23")
    version_number = args.uautomizer_version.replace("uautomizer", "")
    
    # Use explicit output_dir if provided, otherwise save directly to evaluation directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
        evaluation_folder_name = evaluation_dir.name
        output_dir = output_dir / evaluation_folder_name / version_number
    else:
        output_dir = evaluation_dir / version_number
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get metadata
    verifier_versions = get_verifier_version(verifier_executable_path)
    system_info = get_system_info()
    
    # Detect runtime configuration dynamically
    detected_config = get_runtime_configuration(verifier_executable_path)
    
    # Build configuration: use detected values only
    configuration = {
        "per_instance_timeout_seconds": args.timeout,
        "uautomizer_java_heap_max_gb": detected_config.get('uautomizer_java_heap_max_gb'),
        "slurm_cpus_per_task": detected_config.get('slurm_cpus_per_task'),
        "slurm_memory_gb": detected_config.get('slurm_memory_gb')
    }
    
    print(f"UAutomizer version: {args.uautomizer_version} (saving to: {output_dir})")
    print(f"UAutomizer --ultversion: {verifier_versions.get('ultversion', 'unknown')}")
    print(f"UAutomizer --version: {verifier_versions.get('version', 'unknown')}")
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
    
    for yml_file in tqdm(problems, total=len(problems), desc="Processing problems"):
        # print(f"\n[{i}/{len(problems)}] Processing {yml_file.name}")
        
        try:
            result = process_problem(
                yml_file=yml_file,
                uautomizer_path=verifier_executable_path,
                timeout_seconds=args.timeout
            )
            results.append(result)
            
            # print(f"  Result: {result['decision']}")
            # print(f"  Time: {result['baseline_timing']:.2f}s")
            
        except Exception as e:
            print(f"  Error processing {yml_file.name}: {e}")
            # Add error result (using same keys as normal result)
            error_result = {
                "file": yml_file.stem,
                "time": 0.0,
                "result": "ERROR",
                "error_message": str(e)
            }
            results.append(error_result)
        
    total_time = time.time() - start_time
    
    # Create metadata
    metadata = {
        "verifier_versions": verifier_versions,
        "system_info": system_info,
        "configuration": configuration,
        "total_problems": len(problems),
        "total_time": total_time,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "evaluation_folder": str(evaluation_dir),
        "timeout_seconds": args.timeout
    }
    
    # Save metadata separately
    metadata_file = output_dir / f"baseline_metadata{version_number}.json"
    try:
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"\nMetadata saved successfully to: {metadata_file}")
    except Exception as e:
        print(f"\nERROR: Failed to save metadata to {metadata_file}: {e}")
        raise
    
    # Save results as CSV with version number
    csv_file = output_dir / f"baseline_timing{version_number}.csv"
    try:
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(['file', 'result', 'time'])
            # Write data rows
            for row in results:
                writer.writerow([
                    row.get('file', ''),
                    row.get('result', ''),
                    row.get('time', 0)
                ])
        print(f"CSV results saved to: {csv_file}")
    except Exception as e:
        print(f"\nWARNING: Failed to save CSV to {csv_file}: {e}")
    
    print("\n=== Baseline Complete ===")
    print(f"Processed {len(problems)} problems in {total_time:.2f}s")
    print(f"Metadata saved to: {metadata_file}")
    
    # Summary statistics
    decisions = [r["result"] for r in results]
    decision_counts = {}
    for decision in decisions:
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    
    print("\nDecision summary:")
    for decision, count in decision_counts.items():
        print(f"  {decision}: {count}")
    
    # Split full dataset into easy, hard, and unknowns if evaluation folder is 'full' and flag is set
    if evaluation_dir.name == "full" and args.do_split:
        split_full_to_easy_hard_unknowns(
            evaluation_dir=evaluation_dir,
            results=results,
            output_dir=output_dir
        )
    
    # Generate plots for full dataset and splits
    if evaluation_dir.name == "full":
        generate_timing_plots(
            results=results,
            output_dir=output_dir,
            timeout_seconds=args.timeout
        )


def split_full_to_easy_hard_unknowns(
    evaluation_dir: Path,
    results: List[Dict[str, Any]],
    output_dir: Path
) -> None:
    """
    Split full dataset into easy, hard, and unknowns based on baseline timing.
    Easy: timing <= 30 seconds and result is TRUE or FALSE
    Hard: timing > 30 seconds and result is TRUE or FALSE
    Unknowns: result is UNKNOWN, ERROR, or timeout
    
    Splits are saved inside the output_dir (e.g., output_dir/easy, output_dir/hard, output_dir/unknowns).
    """
    print("\n=== Splitting full dataset into easy, hard, and unknowns ===")
    
    # Paths - save splits inside the version directory (e.g., full/23/easy, full/23/hard, full/23/unknowns)
    easy_dir = output_dir / "easy"
    hard_dir = output_dir / "hard"
    unknowns_dir = output_dir / "unknowns"
    
    # Create output directories
    for dest_dir in [easy_dir, hard_dir, unknowns_dir]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "c").mkdir(exist_ok=True)
        (dest_dir / "yml").mkdir(exist_ok=True)
    
    # Create lookup: filename -> (timing, result)
    timing_lookup = {}
    for r in results:
        filename = r.get("file", "")
        timing = r.get("time", 0.0)
        result = r.get("result", "UNKNOWN")
        timing_lookup[filename] = (timing, result)
    
    # Split by timing and result
    easy_files = []
    hard_files = []
    unknown_files = []
    
    for filename, (timing, result) in timing_lookup.items():
        # Unknowns: UNKNOWN, ERROR, or timeout
        if result in ["UNKNOWN", "ERROR"] or timing <= 0:
            unknown_files.append(filename)
        elif timing <= 30:
            easy_files.append(filename)
        else:
            hard_files.append(filename)
    
    # Copy files function
    def copy_files(base_filenames, dest_dir):
        for base_filename in base_filenames:
            src_yml = evaluation_dir / "yml" / f"{base_filename}.yml"
            if not src_yml.exists():
                print(f"Warning: YML file not found: {src_yml}")
                continue
            
            # Get actual C filename from yml
            try:
                yml_data = load_yaml_file(src_yml)
                c_filename = yml_data.get("input_files", f"{base_filename}.c")
                if isinstance(c_filename, list):
                    c_filename = c_filename[0] if c_filename else f"{base_filename}.c"
            except Exception:
                c_filename = f"{base_filename}.c"
            
            src_c = evaluation_dir / "c" / c_filename
            dst_c = dest_dir / "c" / c_filename
            dst_yml = dest_dir / "yml" / f"{base_filename}.yml"
            
            if src_c.exists():
                shutil.copy2(src_c, dst_c)
            else:
                print(f"Warning: C file not found: {src_c}")
            
            shutil.copy2(src_yml, dst_yml)
    
    # Copy files to respective directories
    copy_files(easy_files, easy_dir)
    copy_files(hard_files, hard_dir)
    copy_files(unknown_files, unknowns_dir)
    
    print(f"Easy: {len(easy_files)} problems (timing <= 30s, result: TRUE/FALSE)")
    print(f"Hard: {len(hard_files)} problems (timing > 30s, result: TRUE/FALSE)")
    print(f"Unknowns: {len(unknown_files)} problems (UNKNOWN/ERROR/timeout)")
    print("\nSplit complete! Files saved to:")
    print(f"  - {easy_dir}")
    print(f"  - {hard_dir}")
    print(f"  - {unknowns_dir}")


def plot_timing_distribution(results: List[Dict[str, Any]], title: str, output_path: Path, timeout_seconds: int = 600) -> None:
    """
    Plot timing distribution similar to timing_comparison.ipynb.
    
    Args:
        results: List of result dictionaries with 'file', 'result', 'time' keys
        title: Title for the plot
        output_path: Path to save the plot
        timeout_seconds: Timeout value for the title
    """
    # Convert results to list of times
    times = [r.get('time', 0.0) for r in results]
    
    if not times:
        print(f"Warning: No data to plot for {title}")
        return
    
    # Count number of UNKNOWN in result column
    num_unknown = sum(1 for r in results if r.get('result', '') == 'UNKNOWN')
    
    # Only consider rows that are not UNKNOWN for easy/hard
    non_unknown = [r for r in results if r.get('result', '') != 'UNKNOWN']
    
    # Easy: time <= 30 and result != UNKNOWN
    num_easy = sum(1 for r in non_unknown if r.get('time', 0.0) <= 30)
    # Hard: time > 30 and result != UNKNOWN
    num_hard = sum(1 for r in non_unknown if r.get('time', 0.0) > 30)
    
    # Count number of duplicate rows (by file name)
    files = [r.get('file', '') for r in results]
    num_duplicates = len(files) - len(set(files))
    
    # Compute statistics
    time_min = min(times)
    time_max = max(times)
    time_mean = sum(times) / len(times)
    sorted_times = sorted(times)
    time_median = sorted_times[len(sorted_times) // 2] if sorted_times else 0.0
    
    plt.figure(figsize=(10, 6))
    n, bins, patches = plt.hist(times, bins=50, color='skyblue', edgecolor='black', label=None)
    plt.axvline(30, color='red', linestyle='--', linewidth=2, label='30 seconds')
    
    plot_title = (
        f'{title} ({len(results)} samples), Timeout: {timeout_seconds}\n'
        f'Easy (≤30s): {num_easy} | Hard (>30s): {num_hard} | Duplicates: {num_duplicates}'
    )
    if num_unknown > 0:
        plot_title += f' | Unknowns: {num_unknown}'
    plt.title(plot_title)
    plt.xlabel('Time')
    plt.ylabel('Frequency')
    plt.grid(axis='y')
    
    # First legend: threshold line (upper left)
    legend1 = plt.legend(loc='upper left')
    
    # Second legend: statistics (move to the right: upper right)
    stats_legend_text = (
        f"min = {time_min:.2f}\n"
        f"max = {time_max:.2f}\n"
        f"mean = {time_mean:.2f}\n"
        f"median = {time_median:.2f}"
    )
    dummy_patch = mpatches.Patch(color='none', label=stats_legend_text)
    plt.legend(handles=[dummy_patch], loc='upper right', title='Statistics')
    plt.gca().add_artist(legend1)
    
    # Save the plot
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Plot saved to: {output_path}")


def generate_timing_plots(
    results: List[Dict[str, Any]],
    output_dir: Path,
    timeout_seconds: int = 600
) -> None:
    """
    Generate timing distribution plots for full, easy, hard, and unknown splits.
    
    Args:
        results: List of result dictionaries
        output_dir: Directory to save plots (e.g., full/23)
        timeout_seconds: Timeout value for plots
    """
    print("\n=== Generating timing distribution plots ===")
    
    # Create plots directory
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    # Plot for full dataset
    full_plot_path = plots_dir / "full_distribution.png"
    plot_timing_distribution(results, "Full Dataset", full_plot_path, timeout_seconds)
    
    # Split results into easy, hard, and unknown
    non_unknown = [r for r in results if r.get('result', '') not in ['UNKNOWN', 'ERROR'] and r.get('time', 0.0) > 0]
    easy_results = [r for r in non_unknown if r.get('time', 0.0) <= 30]
    hard_results = [r for r in non_unknown if r.get('time', 0.0) > 30]
    unknown_results = [r for r in results if r.get('result', '') in ['UNKNOWN', 'ERROR'] or r.get('time', 0.0) <= 0]
    
    # Plot for easy split
    if easy_results:
        easy_plot_path = plots_dir / "easy_distribution.png"
        plot_timing_distribution(easy_results, "Easy Split (≤30s)", easy_plot_path, timeout_seconds)
    
    # Plot for hard split
    if hard_results:
        hard_plot_path = plots_dir / "hard_distribution.png"
        plot_timing_distribution(hard_results, "Hard Split (>30s)", hard_plot_path, timeout_seconds)
    
    # Plot for unknown split
    if unknown_results:
        unknown_plot_path = plots_dir / "unknown_distribution.png"
        plot_timing_distribution(unknown_results, "Unknown Split", unknown_plot_path, timeout_seconds)
    print(f"Plots saved to: {plots_dir}")


if __name__ == "__main__":
    main()
    
    