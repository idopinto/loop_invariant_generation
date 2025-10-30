# Baseline Evaluation Script

This directory contains scripts for running UAutomizer baseline evaluation on the InvBench dataset.

## Files

- `src/eval/baseline.py` - Main baseline evaluation script
- `scripts/run_baseline_easy.sbatch` - SLURM batch script for running on easy dataset
- `BASELINE_USAGE.md` - Detailed usage documentation

## Quick Start

### Option 1: Run with SLURM (Recommended for large datasets)

```bash
# Submit job to SLURM queue
sbatch scripts/run_baseline_easy.sbatch

# Check job status
squeue -u $USER

# Monitor output
tail -f baseline_easy_<job_id>.out
```

### Option 2: Run directly (for testing or small datasets)

```bash
# Run on easy dataset with 30 second timeout
python src/eval/baseline.py dataset/evaluation/easy --timeout 30 --output-dir baseline_results

# Run on hard dataset
python src/eval/baseline.py dataset/evaluation/hard --timeout 60 --output-dir baseline_results
```

## Output Structure

The script creates results in the following structure:

```
baseline_results/
└── easy/                           # Named after evaluation folder
    ├── baseline_results.json       # Updated incrementally as processing
    └── metadata.json               # System info and run metadata
```

## Key Features

- **Incremental Results**: `baseline_results.json` is updated after each problem is processed
- **No Log Files**: Only final JSON results are saved (no verbose logs)
- **Metadata Separation**: System info saved separately in `metadata.json`
- **Error Handling**: Continues processing even if individual problems fail
- **Progress Tracking**: Shows progress and timing for each problem

## Monitoring Progress

Since results are written incrementally, you can monitor progress:

```bash
# Watch results file grow
watch -n 5 'wc -l baseline_results/easy/baseline_results.json'

# Check current progress
jq 'length' baseline_results/easy/baseline_results.json

# View latest results
tail -n 20 baseline_results/easy/baseline_results.json
```

## SLURM Job Configuration

The sbatch script is configured with:
- **Time Limit**: 2 hours (adjust if needed for larger datasets)
- **Memory**: 4GB (sufficient for UAutomizer)
- **CPUs**: 1 (UAutomizer is single-threaded)
- **Partition**: short (adjust based on your cluster)

## Expected Runtime

- **Easy Dataset**: ~133 problems × 30s timeout = ~1-2 hours
- **Hard Dataset**: Longer runtime due to more complex problems

## Troubleshooting

1. **Job Timeout**: Increase `--time` in sbatch script
2. **Memory Issues**: Increase `--mem` in sbatch script  
3. **Permission Errors**: Ensure write access to output directory
4. **UAutomizer Not Found**: Check path in script configuration

## Results Analysis

After completion, analyze results:

```bash
# Count decisions
jq '[.[].decision] | group_by(.) | map({decision: .[0], count: length})' baseline_results/easy/baseline_results.json

# Average timing
jq '[.[].baseline_timing] | add / length' baseline_results/easy/baseline_results.json

# View metadata
cat baseline_results/easy/metadata.json
```
