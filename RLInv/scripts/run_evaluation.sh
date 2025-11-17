#!/bin/bash
#SBATCH --job-name=evaluation
#SBATCH --output=slurm/evaluation_%j.out
#SBATCH --error=slurm/evaluation_%j.err
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G

# Script to run evaluation using the unified evaluator
# Usage: sbatch run_evaluation.sh <exp_id> <data_split> [OPTIONS]
# Usage: ./run_evaluation.sh <exp_id> <data_split> [OPTIONS]

set -e

if [ $# -lt 2 ]; then
    echo "Usage: $0 <exp_id> <data_split> [OPTIONS]"
    echo ""
    echo "Required arguments:"
    echo "  exp_id: Experiment ID (e.g., 001, test_run_001)"
    echo "  data_split: Data split (easy or hard)"
    echo ""
    echo "Optional arguments:"
    echo "  --baseline_dir <dir>            Baseline directory (default: uautomizer25_evaluation_k3_rewrite)"
    echo "  --limit <n>                     Limit number of tasks (default: -1 for all)"
    echo "  --default_timeout_seconds <n>   Timeout in seconds (default: 600)"
    echo "  --property_kind <kind>          Property kind (default: unreach)"
    echo "  --prefix <prefix>               Prefix for dataset files"
    echo "  --suffix <suffix>               Suffix for dataset files"
    echo "  --compute_metrics               Compute and save metrics"
    echo ""
    echo "Example: sbatch run_evaluation.sh test_001 easy --limit 10 --compute_metrics"
    exit 1
fi

EXP_ID=$1
DATA_SPLIT=$2
shift 2

# Validate data split
if [[ ! "$DATA_SPLIT" =~ ^(easy|hard)$ ]]; then
    echo "Error: Data split must be 'easy' or 'hard'"
    exit 1
fi

# Set working directory
cd "/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv"
mkdir -p slurm

# Activate venv if exists
[ -f ".venv/bin/activate" ] && source .venv/bin/activate

# Display configuration
echo "=========================================="
echo "Running Model Evaluation"
echo "Job ID: ${SLURM_JOB_ID:-N/A}"
echo "Experiment ID: $EXP_ID"
echo "Data Split: $DATA_SPLIT"
echo "Start time: $(date)"
echo "=========================================="

# Run evaluation
uv run src/eval/evaluate.py --exp_id "$EXP_ID" --data_split "$DATA_SPLIT" "$@"

echo ""
echo "=========================================="
echo "Evaluation completed at $(date)"
echo "Results: experiments/${EXP_ID}/"
echo "=========================================="
