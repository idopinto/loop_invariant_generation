#!/bin/bash
#SBATCH --job-name=eval-self-gen-invs
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=slurm/eval_self_%j.out
#SBATCH --error=slurm/eval_self_%j.err
set -e
cd /cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv

source .venv/bin/activate

srun python -u src/eval/evaluate_self_gen_invs.py \
  --json-file dataset/training/uautomizer25_training_k1_rewrite/uautomizer25_training_k1_rewrite.json \
  --uautomizer-version 25 \
  --output-dir experiments/uautomizer_self_verification_usefulness \
  --timeout 600 \
  --limit 250

