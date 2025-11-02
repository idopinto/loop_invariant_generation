#!/bin/bash
#SBATCH --job-name=experiment
#SBATCH --output=slurm/experiment_%j.out
#SBATCH --error=slurm/experiment_%j.err
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G

# Script to run experiment evaluation on models
# Usage: sbatch run_experiment.sh <exp_id> <data_split> <models...> [--limit <limit>] [--include_model_generation_time] [--default_timeout_seconds <timeout>] [--property_kind <kind>]
# Usage: ./run_experiment.sh <exp_id> <data_split> <models...> [--limit <limit>] [--include_model_generation_time] [--default_timeout_seconds <timeout>] [--property_kind <kind>]

set -e

# Check minimum arguments
if [ $# -lt 3 ]; then
    echo "Usage: $0 <exp_id> <data_split> <model1> [<model2> ...] [OPTIONS]"
    echo ""
    echo "Required arguments:"
    echo "  exp_id: Experiment ID (e.g., 001, test_run_001)"
    echo "  data_split: Data split (easy or hard)"
    echo "  model: Model name or path (can specify multiple, space-separated)"
    echo ""
    echo "Optional arguments:"
    echo "  --limit <n>                    Limit number of tasks to evaluate (default: -1 for all)"
    echo "  --include_model_generation_time Include model generation time in speedup calculations"
    echo "  --default_timeout_seconds <n>  Default timeout seconds for verification (default: 600)"
    echo "  --property_kind <kind>         Property kind (default: unreach)"
    echo ""
    echo "Example:"
    echo "  sbatch run_experiment.sh test_001 easy gpt-oss-20b --limit 10"
    echo "  sbatch run_experiment.sh exp_002 hard model1 model2 --limit 5 --default_timeout_seconds 900"
    exit 1
fi

EXP_ID=$1
DATA_SPLIT=$2
shift 2  # Remove first two arguments

# Validate split
if [ "$DATA_SPLIT" != "easy" ] && [ "$DATA_SPLIT" != "hard" ]; then
    echo "Error: Data split must be 'easy' or 'hard'"
    exit 1
fi

# Parse models and optional arguments
MODELS=()
EXTRA_ARGS=()
PARSING_MODELS=true

while [ $# -gt 0 ]; do
    case $1 in
        --limit)
            PARSING_MODELS=false
            EXTRA_ARGS+=("--limit" "$2")
            shift 2
            ;;
        --include_model_generation_time)
            PARSING_MODELS=false
            EXTRA_ARGS+=("--include_model_generation_time")
            shift
            ;;
        --default_timeout_seconds)
            PARSING_MODELS=false
            EXTRA_ARGS+=("--default_timeout_seconds" "$2")
            shift 2
            ;;
        --property_kind)
            PARSING_MODELS=false
            EXTRA_ARGS+=("--property_kind" "$2")
            shift 2
            ;;
        *)
            if [ "$PARSING_MODELS" = true ]; then
                MODELS+=("$1")
            else
                echo "Error: Unexpected argument after options: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# Check that at least one model was provided
if [ ${#MODELS[@]} -eq 0 ]; then
    echo "Error: At least one model must be specified"
    exit 1
fi

# Convert models array to space-separated string
MODELS_STR="${MODELS[*]}"

# Set working directory
PROJECT_ROOT="/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv"
cd "$PROJECT_ROOT"

# Create slurm directory if it doesn't exist
mkdir -p slurm

# Activate virtual environment (if exists)
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Display configuration
echo "=========================================="
echo "Running Experiment Evaluation"
echo "=========================================="
echo "Job ID: $SLURM_JOB_ID"
echo "Experiment ID: $EXP_ID"
echo "Data Split: $DATA_SPLIT"
echo "Models: $MODELS_STR"
echo "Start time: $(date)"
echo "=========================================="

# Build command
CMD="uv run src/eval/experiment.py --exp_id $EXP_ID --data_split $DATA_SPLIT --models \"$MODELS_STR\""

# Add extra arguments if any
if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
    CMD="$CMD ${EXTRA_ARGS[*]}"
fi

echo "Command: $CMD"
echo ""

# Run the experiment
eval $CMD

echo ""
echo "=========================================="
echo "Experiment evaluation completed!"
echo "End time: $(date)"
echo "Results saved in: experiments/exp_${EXP_ID}/"
echo "=========================================="

