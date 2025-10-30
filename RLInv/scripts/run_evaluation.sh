#!/usr/bin/env bash

# Script to run evaluation on multiple models and then aggregate results
# Usage: ./run_evaluation.sh <exp_id> <data_split> <model1> [<model2> ...]

set -e  # Exit on error

# Check arguments
if [ $# -lt 3 ]; then
    echo "Usage: $0 <exp_id> <data_split> <model1> [<model2> ...]"
    echo "  exp_id: Experiment ID (e.g., 001)"
    echo "  data_split: Data split (easy or hard)"
    echo "  model: Model name or path (can specify multiple)"
    exit 1
fi

EXP_ID=$1
DATA_SPLIT=$2
LIMIT=$3
shift 3  # Remove first three arguments
MODELS=("$@")  # Remaining arguments are models

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Python evaluation script
EVALUATE_SCRIPT="$PROJECT_ROOT/src/eval/evaluate.py"
EVALUATE_MULTIPLE_SCRIPT="$PROJECT_ROOT/src/eval/evaluate_multiple_models.py"
BASELINE_SCRIPT="$SCRIPT_DIR/run_baseline.sh"

# Baseline results file
BASELINE_FILE="$PROJECT_ROOT/dataset/evaluation/$DATA_SPLIT/baseline_results.json"

# Change to project root
cd "$PROJECT_ROOT"
EVALUATION_FOLDER="dataset/evaluation/$DATA_SPLIT"

echo "=========================================="
echo "Running Evaluation Pipeline"
echo "=========================================="
echo "Experiment ID: $EXP_ID"
echo "Data Split: $DATA_SPLIT"
echo "Models: ${MODELS[*]}"
echo "Limit: $LIMIT"
echo "=========================================="

# Check if baseline results exist, run baseline if not
if [ ! -f "$BASELINE_FILE" ]; then
    echo ""
    echo "--- Baseline results not found for $DATA_SPLIT split ---"
    echo "Running baseline script to generate baseline results..."
    bash "$BASELINE_SCRIPT" "$DATA_SPLIT"
    echo "✓ Baseline results generated"
else
    echo ""
    echo "✓ Baseline results already exist for $DATA_SPLIT split"
    echo "  Location: $BASELINE_FILE"
fi

# Run evaluate.py for each model
for model in "${MODELS[@]}"; do
    echo ""
    echo "--- Evaluating model: $model ---"
    python3 -u "$EVALUATE_SCRIPT" \
        --model_name_or_path "$model" \
        --data_split "$DATA_SPLIT" \
        --exp_id "$EXP_ID" \
        --limit "$LIMIT"
    echo "✓ Completed evaluation for: $model"
done

# After all models are done, run evaluate_multiple_models.py
echo ""
echo "=========================================="
echo "Aggregating results from all models"
echo "=========================================="
python3 -u "$EVALUATE_MULTIPLE_SCRIPT" \
    --exp_id "$EXP_ID" \
    --data_split "$DATA_SPLIT"

echo ""
echo "=========================================="
echo "Evaluation pipeline completed!"
echo "Results saved in: experiments/exp_${EXP_ID}/"
echo "=========================================="

