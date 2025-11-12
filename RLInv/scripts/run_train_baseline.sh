#!/bin/bash
#SBATCH --job-name=train_baseline
#SBATCH --output=slurm/train_baseline_%j.out
#SBATCH --error=slurm/train_baseline_%j.err
#SBATCH --time=4-00:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G

# Script to run train_baseline_with_gt_invariants.py on training/orig_programs dataset
# Usage: sbatch scripts/run_train_baseline.sh [version] [timeout] [limit]
# Usage: ./scripts/run_train_baseline.sh [version] [timeout] [limit]
#   version: 23, 24, 25, or 26 (default: 25)
#   timeout: Timeout in seconds per file (default: 600)
#   limit: Limit number of files to process for testing (optional)

set -e

# Parse arguments
VERSION=${1:-25}
TIMEOUT=${2:-600}
LIMIT=${3:-}

# Validate version
if [ "$VERSION" != "23" ] && [ "$VERSION" != "24" ] && \
   [ "$VERSION" != "25" ] && [ "$VERSION" != "26" ]; then
    echo "Error: Version must be '23', '24', '25', or '26'"
    echo "  Received: '$VERSION'"
    echo ""
    echo "Usage: $0 [version] [timeout] [limit]"
    echo "  version: 23, 24, 25, or 26 (default: 25)"
    echo "  timeout: Timeout in seconds per file (default: 600)"
    echo "  limit: Limit number of files to process for testing (optional)"
    echo ""
    echo "  Example: sbatch $0 25"
    echo "  Example: sbatch $0 25 600 10  # Test with 10 files"
    echo "  Example: ./$0 25"
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

# Run capture training baseline script
echo "Starting training baseline..."
echo "UAutomizer version: $VERSION"
echo "Timeout per file: $TIMEOUT seconds"
if [ -n "$LIMIT" ]; then
    echo "Limit: $LIMIT files (testing mode)"
fi
echo "Job ID: $SLURM_JOB_ID"
echo "Start time: $(date)"
echo "SLURM resources:"
echo "  CPUs: $SLURM_CPUS_PER_TASK"
echo "  Memory: $SLURM_MEM_PER_NODE"
echo "  Time limit: $SLURM_TIME_LIMIT"
echo ""

# Build command
TRAIN_CMD="uv run src/utils/train_baseline_with_gt_invariants.py --uautomizer_version $VERSION --timeout $TIMEOUT"

# Add limit if specified
if [ -n "$LIMIT" ]; then
    TRAIN_CMD="$TRAIN_CMD --limit $LIMIT"
fi

# Run the command
$TRAIN_CMD

echo ""
echo "Training baseline completed!"
echo "End time: $(date)"
echo ""
echo "Results saved in: dataset/training/uautomizer$VERSION_train/"
echo "  - uautomizer$VERSION_train.json"
echo "  - uautomizer$VERSION_train_bad_files.json"

