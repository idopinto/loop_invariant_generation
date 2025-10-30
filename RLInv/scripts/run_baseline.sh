#!/bin/bash
#SBATCH --job-name=baseline
#SBATCH --output=slurm/baseline_hard_%j.out
#SBATCH --error=slurm/baseline__hard_%j.err
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G

# Script to run baseline on easy or hard dataset
# Usage: sbatch run_baseline.sh <easy|hard>
# Usage: ./run_baseline.sh <easy|hard>

set -e

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <easy|hard>"
    echo "  easy: Run baseline on easy dataset"
    echo "  hard: Run baseline on hard dataset"
    exit 1
fi

DATA_SPLIT=$1

# Validate split
if [ "$DATA_SPLIT" != "easy" ] && [ "$DATA_SPLIT" != "hard" ]; then
    echo "Error: Data split must be 'easy' or 'hard'"
    exit 1
fi

# Set working directory
cd /cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv
source .venv/bin/activate
which python

# Run baseline script on evaluation dataset
echo "Starting baseline evaluation on $DATA_SPLIT dataset..."
echo "Job ID: $SLURM_JOB_ID"
echo "Start time: $(date)"
uv run src/eval/baseline.py dataset/evaluation/$DATA_SPLIT --timeout 600

echo "Baseline evaluation completed!"
echo "End time: $(date)"
echo "Results saved in: dataset/evaluation/$DATA_SPLIT/"
