#!/bin/bash
#SBATCH --job-name=baseline
#SBATCH --output=slurm/baseline_full_%j.out
#SBATCH --error=slurm/baseline_full_%j.err
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G

# Script to run baseline on evaluation dataset
# Usage: sbatch scripts/run_baseline_full.sh <easy|hard|full|single> [uautomizer_version]
# Usage: ./scripts/run_baseline_full.sh <easy|hard|full|single> [uautomizer_version]
#   uautomizer_version: uautomizer23, uautomizer24, uautomizer25, or uautomizer26 (default: uautomizer23)

set -e

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <easy|hard|full|single> [uautomizer_version]"
    echo "  easy: Run baseline on easy dataset"
    echo "  hard: Run baseline on hard dataset"
    echo "  full: Run baseline on full dataset (all unique problems)"
    echo "  single: Run baseline on single test problem (for testing)"
    echo ""
    echo "  uautomizer_version (optional): uautomizer23, uautomizer24, uautomizer25, or uautomizer26"
    echo "    Default: uautomizer23"
    exit 1
fi

DATA_SPLIT=$1
UAUTOMIZER_VERSION=${2:-uautomizer23}

# Debug: Show what arguments were received
echo "Debug: Received $# arguments"
echo "Debug: Argument 1 (DATA_SPLIT): '$DATA_SPLIT'"
echo "Debug: Argument 2 (UAUTOMIZER_VERSION): '$UAUTOMIZER_VERSION'"

# Validate split
if [ "$DATA_SPLIT" != "easy" ] && [ "$DATA_SPLIT" != "hard" ] && [ "$DATA_SPLIT" != "full" ] && [ "$DATA_SPLIT" != "single" ]; then
    echo "Error: Data split must be 'easy', 'hard', 'full', or 'single'"
    echo "  Received: '$DATA_SPLIT'"
    echo ""
    echo "Usage: $0 <easy|hard|full|single> [uautomizer_version]"
    echo "  Example: sbatch $0 full uautomizer23"
    echo "  Example: ./$0 full"
    exit 1
fi

# Validate UAutomizer version
if [ "$UAUTOMIZER_VERSION" != "uautomizer23" ] && [ "$UAUTOMIZER_VERSION" != "uautomizer24" ] && \
   [ "$UAUTOMIZER_VERSION" != "uautomizer25" ] && [ "$UAUTOMIZER_VERSION" != "uautomizer26" ]; then
    echo "Error: UAutomizer version must be 'uautomizer23', 'uautomizer24', 'uautomizer25', or 'uautomizer26'"
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
echo "UAutomizer version: $UAUTOMIZER_VERSION"
echo "Job ID: $SLURM_JOB_ID"
echo "Start time: $(date)"
echo "SLURM resources:"
echo "  CPUs: $SLURM_CPUS_PER_TASK"
echo "  Memory: $SLURM_MEM_PER_NODE"
echo "  Time limit: $SLURM_TIME_LIMIT"
echo "Timeout per problem: $TIMEOUT seconds"

# Build command with appropriate flags
BASELINE_CMD="uv run src/eval/baseline.py dataset/evaluation/$DATA_SPLIT --uautomizer_version $UAUTOMIZER_VERSION --timeout $TIMEOUT"

# Add --do-split flag for full dataset
if [ "$DATA_SPLIT" == "full" ]; then
    BASELINE_CMD="$BASELINE_CMD --do-split"
    echo "Running with --do-split flag (will create easy/hard/unknown splits)"
fi

# Run the command
$BASELINE_CMD

echo ""
echo "Baseline evaluation completed!"
echo "End time: $(date)"
echo ""
echo "Results saved in: dataset/evaluation/$DATA_SPLIT/"

# Extract version number from uautomizer version (e.g., uautomizer23 -> 23)
VERSION_NUM=$(echo "$UAUTOMIZER_VERSION" | sed 's/uautomizer//')

# Check for version-specific directories (e.g., 23/, 24/, etc.)
if [ "$DATA_SPLIT" == "full" ]; then
    echo ""
    echo "Results are saved in: dataset/evaluation/$DATA_SPLIT/$VERSION_NUM/"
    echo "  - baseline_timing.json"
    echo "  - baseline_timing${VERSION_NUM}.csv"
    echo "  - baseline_metadata${VERSION_NUM}.json"
    echo "  - plots/"
    echo "    - full_distribution.png"
    echo "    - easy_distribution.png"
    echo "    - hard_distribution.png"
    echo "    - unknown_distribution.png"
    echo ""
    echo "Splits are saved in: dataset/evaluation/$DATA_SPLIT/$VERSION_NUM/"
    echo "  - easy/ (timing <= 30s, result: TRUE/FALSE)"
    echo "  - hard/ (timing > 30s, result: TRUE/FALSE)"
    echo "  - unknowns/ (UNKNOWN/ERROR/timeout)"
else
    echo "  - baseline_timing.json"
    echo "  - baseline_metadata.json"
    echo ""
    echo "Version-specific results also saved in: dataset/evaluation/$DATA_SPLIT/$VERSION_NUM/"
    echo "  - baseline_timing${VERSION_NUM}.csv"
fi

