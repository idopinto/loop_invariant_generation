#!/bin/bash
#SBATCH --job-name=build_data
#SBATCH --output=slurm/build_data_%j.out
#SBATCH --error=slurm/build_data_%j.err
#SBATCH --time=72:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G

# sbatch scripts/build_dataset.sh --dataset-type evaluation --k 3--push-to-hub
# sbatch scripts/build_dataset.sh --dataset-type training --k 1 --push-to-hub

set -e

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <dataset-type> <k> <push-to-hub>"
    echo "  dataset-type: training or evaluation"
    echo "  k: number of times to run UAutomizer"
    echo "  push-to-hub: true or false"
    exit 1
fi
echo "Job ID: ${SLURM_JOB_ID:-N/A}"
cd /cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv
[ -d ".venv" ] && source .venv/bin/activate
uv run src/preprocess/build_baseline_dataset.py $@
echo "Completed: $(date)"