#!/bin/bash
#SBATCH --job-name=baseline
#SBATCH --output=slurm/baseline_%j.out
#SBATCH --error=slurm/baseline_%j.err
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G

# Usage: sbatch scripts/run_new_baseline.sh <training|evaluation> [version] [timeout] [k] [limit] [rewrite] [prefix]
#   version: 23, 24, 25, or 26 (default: 25)
#   timeout: seconds (default: 600)
#   k: number of runs per file for median calculation (default: 1)
#   limit: number of files for testing (optional)
#   rewrite: set to "rewrite" to enable rewrite mode (optional)
#   prefix: prefix to filter files by (optional)
#   
# sbatch scripts/run_new_baseline.sh evaluation 25 600 3 2 rewrite "test_"

set -e

[ $# -lt 1 ] && { echo "Usage: $0 <training|evaluation> [version] [timeout] [k] [limit] [rewrite] [prefix]"; exit 1; }

DATASET_TYPE=$1
UAUTOMIZER_VERSION=${2:-25}
TIMEOUT=${3:-600}
K=${4:-1}
LIMIT=${5:-}
REWRITE=${6:-}
PREFIX=${7:-}

[[ "$DATASET_TYPE" =~ ^(training|evaluation)$ ]] || { echo "Error: dataset_type must be 'training' or 'evaluation'"; exit 1; }
[[ "$UAUTOMIZER_VERSION" =~ ^(23|24|25|26)$ ]] || { echo "Error: version must be 23, 24, 25, or 26"; exit 1; }

cd /cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv
[ -d ".venv" ] && source .venv/bin/activate

echo "Running baseline: $DATASET_TYPE, version $UAUTOMIZER_VERSION, timeout ${TIMEOUT}s, k=${K}${LIMIT:+, limit $LIMIT}${REWRITE:+, rewrite enabled}${PREFIX:+, prefix: $PREFIX}"
[ -n "$SLURM_JOB_ID" ] && echo "Job ID: $SLURM_JOB_ID, Start: $(date)"

BASELINE_CMD="uv run src/utils/get_baseline.py --dataset_type $DATASET_TYPE --uautomizer_version $UAUTOMIZER_VERSION --timeout $TIMEOUT --k $K"
[ -n "$LIMIT" ] && BASELINE_CMD="$BASELINE_CMD --limit $LIMIT"
[ -n "$REWRITE" ] && BASELINE_CMD="$BASELINE_CMD --rewrite"
[ -n "$PREFIX" ] && BASELINE_CMD="$BASELINE_CMD --prefix $PREFIX"

$BASELINE_CMD

echo "Completed: $(date)"
if [ "$K" -eq 1 ]; then
    echo "Results: dataset/$DATASET_TYPE/uautomizer${UAUTOMIZER_VERSION}_${DATASET_TYPE}/"
else
    echo "Results: dataset/$DATASET_TYPE/uautomizer${UAUTOMIZER_VERSION}_${DATASET_TYPE}_k${K}/"
fi
