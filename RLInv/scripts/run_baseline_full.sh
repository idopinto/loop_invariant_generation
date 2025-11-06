#!/bin/bash
#SBATCH --job-name=baseline
#SBATCH --output=slurm/baseline_full_%j.out
#SBATCH --error=slurm/baseline_full_%j.err
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G

# Script to run baseline on evaluation dataset
# Usage: sbatch scripts/run_baseline_full.sh <easy|hard|full|single>
# Usage: ./scripts/run_baseline_full.sh <easy|hard|full|single>

set -e

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <easy|hard|full|single>"
    echo "  easy: Run baseline on easy dataset"
    echo "  hard: Run baseline on hard dataset"
    echo "  full: Run baseline on full dataset (all unique problems)"
    echo "  single: Run baseline on single test problem (for testing)"
    exit 1
fi

DATA_SPLIT=$1

# Validate split
if [ "$DATA_SPLIT" != "easy" ] && [ "$DATA_SPLIT" != "hard" ] && [ "$DATA_SPLIT" != "full" ] && [ "$DATA_SPLIT" != "single" ]; then
    echo "Error: Data split must be 'easy', 'hard', 'full', or 'single'"
    exit 1
fi

# Set working directory
cd /cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Verify Python
which python
python --version

# Adjust timeout for single test
if [ "$DATA_SPLIT" == "single" ]; then
    TIMEOUT=60
else
    TIMEOUT=600
fi

# Run baseline script on evaluation dataset
echo "Starting baseline evaluation on $DATA_SPLIT dataset..."
echo "Job ID: $SLURM_JOB_ID"
echo "Start time: $(date)"
echo "SLURM resources:"
echo "  CPUs: $SLURM_CPUS_PER_TASK"
echo "  Memory: $SLURM_MEM_PER_NODE"
echo "  Time limit: $SLURM_TIME_LIMIT"
echo "Timeout per problem: $TIMEOUT seconds"

uv run src/eval/baseline.py dataset/evaluation/$DATA_SPLIT --timeout $TIMEOUT

echo ""
echo "Baseline evaluation completed!"
echo "End time: $(date)"
echo "Results saved in: dataset/evaluation/$DATA_SPLIT/"
echo "  - baseline_timing.json"
echo "  - baseline_metadata.json"

