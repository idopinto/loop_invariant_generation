#!/bin/bash
#SBATCH --job-name=eval-self-gen-invs
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --output=slurm/eval_self_test_%j.out
#SBATCH --error=slurm/eval_self_test_%j.err
set -e
cd /cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv

source .venv/bin/activate

srun python -u src/eval/evaluate_self_gen_invs.py \
  --json-file dataset/training/uautomizer25_training_k1_rewrite_/uautomizer25_training_k1_rewrite_filtered.json \
  --uautomizer-version 25 \
  --output-dir uautomizer25_eval_self_gen_invs \
  --timeout 600 \
  --limit 500 \
  # --timeout-is-baseline