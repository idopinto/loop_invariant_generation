# Baseline Script Usage Examples

## Basic Usage
```bash
# Run baseline on easy evaluation problems
python src/eval/baseline.py dataset/evaluation/easy

# Run with custom timeout and output directory
python src/eval/baseline.py dataset/evaluation/easy --timeout 60 --output-dir my_baseline_results
```

## Output Structure
The script creates a `baseline_results` folder (or custom directory) with two files:

### 1. `metadata.json` - System and run information
```json
{
  "uautomizer_version": "d790fecc",
  "system_info": {
    "os": "Linux 6.12.32-aufs-1",
    "architecture": "x86_64",
    "cpu": "AMD EPYC 7452 32-Core Processor",
    "memory": "528198500 kB",
    "python_version": "3.13.5"
  },
  "total_problems": 133,
  "total_time": 1234.56,
  "timestamp": "2025-01-27 10:30:45",
  "evaluation_folder": "dataset/evaluation/easy",
  "timeout_seconds": 300
}
```

### 2. `baseline_results.json` - Verification results
```json
[
  {
    "base_filename": "benchmark24_conjunctive_1",
    "decision": "Verified",
    "baseline_timing": 2.34,
    "timeout": false,
    "error": false,
    "architecture": "32bit",
    "property_file": "/path/to/unreach-call.prp",
    "expected_answer": true
  }
]
```

## Key Features
- Uses existing Task class and utils for consistency
- Collects UAutomizer version and system hardware info for fair comparison
- Measures precise timing for each verification
- Handles errors gracefully and continues processing
- **No log files saved** - only final JSON results
- Separates metadata from results for easier analysis
- Provides summary statistics at the end
