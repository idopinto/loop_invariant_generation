sbatch scripts/run_evaluation.sh oss_exp_full easy --limit -1 --compute_metrics --baseline_is_timeout
sbatch scripts/run_evaluation.sh oss_exp_full easy --limit -1 --compute_metrics 
sbatch scripts/run_evaluation.sh oss_exp_full hard --limit -1 --compute_metrics --baseline_is_timeout
sbatch scripts/run_evaluation.sh oss_exp_full hard --limit -1 --compute_metrics 