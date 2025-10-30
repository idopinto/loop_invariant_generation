Evaluation Data:
InvBench-Easy: 133 samples only
Category: ReachSafety (Only?)

Training Data:
InvBench-train: 3589 samples only

I am completly Ignore the llm-based verifiers tools like lemur and loopy for now.

Task:
Given a program P and a target property p⋆, the system must generate candidate invariants q and evaluate them according to the decision procedure.
When proposing an invariant q = ⟨ψ, l⟩, the model selects a program location l and supplies the corresponding predicate ψ.

model:
gpt-oss-20b
ai21 model 3b

1. replicate the evaluation code.
2. run one model on the InvBench-Easy and get results.
3. write training code for SFT 
4. write training code for RL (GRPO)
    a. reward engineering
        - correctness
        - absoulte time / relative time (negative logarithm)
        - houdini-based survivel rate.
        ## BEWARE of Reward Hacking
    b. curriculum learning (problems with ascending verification time)
    