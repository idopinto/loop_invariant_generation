import json
from pathlib import Path
from datasets import Dataset
from datasets import load_dataset
from tqdm import tqdm
DATA_DIR = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/dataset/training")
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)




def create_train_data_for_sft_not_separated(train_data_path: Path, full_hf_dataset_name: str, save_to_disk: bool = False, push_to_hub: bool = False) -> list:
    logger.info(f"Creating train data for SFT from {train_data_path}")
    logger.info(f"Full HF dataset name: {full_hf_dataset_name}")
    logger.info(f"Saving to disk: {save_to_disk}, pushing to hub: {push_to_hub}")
    system_prompt = "You understand C programs well and can generate strong loop invariants for program verification."
    user_prompt_template = """Given the following C program, generate only {num_invariants} loop invariants for each of the marked lines:
```c
{formatted_program}
```

Format:
assert(<invariant_1>); // Line A
assert(<invariant_2>); // Line B
...

Example:
assert(a > 0 && a < 10); // Line A
assert(b > 0 && b < 20); // Line B
...
"""

    with open(train_data_path, "r") as f:
        train_data = json.load(f)

    # train_data = train_data[:1]
    samples = []
    for data_point in tqdm(train_data):
        rf_program_lines = data_point["rf_program"].split("\n")
        invariants = data_point["invariants"]
        # Insert invariants from bottom to top (highest line number first)
        # This avoids having to track line number offsets
        sorted_invariants = sorted(invariants, key=lambda x: x['line'], reverse=True)
        start_letter = 'A'
        line_map = {}
        for inv_data in sorted_invariants:
            line_number = inv_data['line']
            rf_program_lines.insert(line_number, f"// Line {start_letter}")
            line_map[line_number] = start_letter
            start_letter = chr(ord(start_letter) + 1) 
        print(rf_program_lines)
        print(line_map)
        formatted_program = "\n".join(rf_program_lines)
        print(formatted_program)
        answer = "\n".join([f"assert({inv_data['invariant']}); // Line {line_map[inv_data['line']]}" for inv_data in sorted_invariants])
        sample = {"messages": [
            {"role": "system", "content": system_prompt, "thinking": None},
            {"role": "user", "content": user_prompt_template.format(formatted_program=formatted_program, num_invariants=len(sorted_invariants)), "thinking": None},
            {"role": "assistant", "content": answer, "thinking": None}
        ]}
        samples.append(sample)

    hf_dataset = Dataset.from_list(samples)
    if save_to_disk:
        hf_data_dir = DATA_DIR / "hf_datasets"
        hf_data_dir.mkdir(parents=True, exist_ok=True)
        hf_dataset.save_to_disk(hf_data_dir / full_hf_dataset_name.replace("/", "_"))
    if push_to_hub:
        hf_dataset.push_to_hub(full_hf_dataset_name)
    return hf_dataset


def create_train_data_for_sft_separated_invariants(train_data_path: Path, full_hf_dataset_name: str, save_to_disk: bool = False, push_to_hub: bool = False) -> list:
    logger.info(f"Creating train data for SFT from {train_data_path}")
    logger.info(f"Full HF dataset name: {full_hf_dataset_name}")
    logger.info(f"Saving to disk: {save_to_disk}, pushing to hub: {push_to_hub}")
    system_prompt = "You understand C programs well and can generate strong loop invariants for program verification."
    user_prompt_template = """Given the following C program, generate only one loop invariant at the marked line with the comment // GENERATE INVARIANT HERE:
```c
{formatted_program}
```
Format:
assert(<invariant>);

Example:
assert(a > 0 && a < 10);
"""

    with open(train_data_path, "r") as f:
        train_data = json.load(f)

    # train_data = train_data[:10]
    samples = []
    for data_point in tqdm(train_data):
        for invariant in data_point["invariants"]:
            rf_program_lines = data_point["rf_program"].split("\n")
            line_number = invariant["line"]
            rf_program_lines.insert(line_number, "// GENERATE INVARIANT HERE")
            formatted_program = "\n".join(rf_program_lines)
            sample = {"messages": [
                {"role": "system", "content": system_prompt, "thinking": None},
                {"role": "user", "content": user_prompt_template.format(
                    formatted_program=formatted_program
                ), "thinking": None},
                {"role": "assistant", "content": f"assert({invariant['invariant']});", "thinking": None}
            ]}
            samples.append(sample)

    hf_dataset = Dataset.from_list(samples)
    if save_to_disk:
        hf_data_dir = DATA_DIR / "hf_datasets"
        hf_data_dir.mkdir(parents=True, exist_ok=True)
        hf_dataset.save_to_disk(hf_data_dir / full_hf_dataset_name.replace("/", "_"))
    if push_to_hub:
        hf_dataset.push_to_hub(full_hf_dataset_name)
    return hf_dataset


def load_train_data_for_sft(hf_dataset_name: str, split: str = "train", load_from_disk: bool = False) -> Dataset:
    if load_from_disk:
        hf_data_dir = DATA_DIR / "hf_datasets"
        hf_data_dir.mkdir(parents=True, exist_ok=True)
        return Dataset.load_from_disk(hf_data_dir / hf_dataset_name)
    else:
        return load_dataset(hf_dataset_name, split=split)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Create train data for SFT")
    parser.add_argument("--uautomizer-version", type=str, default="25", help="UAutomizer version (default: 25)")
    parser.add_argument("--hf-user-name", type=str, default="idopinto", help="HF user name (default: idopinto)")
    parser.add_argument("--hf-dataset-name", type=str, default="gen-inv-sft-for-gpt-oss-full-sep2", help="HF dataset name (default: gen-inv-sft-for-gpt-oss-full2)")
    parser.add_argument("--save-to-disk", action="store_true", help="Save to disk (default: False)")
    parser.add_argument("--push-to-hub", action="store_true", help="Push to hub (default: False)")
    parser.add_argument("--separate-invariants", action="store_true", help="Separate invariants (default: False)")

    args = parser.parse_args()
    logger.info(f"Running with arguments: {args}")
    train_data_path = DATA_DIR / f"uautomizer{args.uautomizer_version}_training_k1_rewrite_" / f"uautomizer{args.uautomizer_version}_training_k1_rewrite_filtered2.json"

    full_hf_dataset_name = f"{args.hf_user_name}/{args.hf_dataset_name}"
    if args.separate_invariants:
        create_train_data_for_sft_separated_invariants(train_data_path=train_data_path, full_hf_dataset_name=full_hf_dataset_name, save_to_disk=args.save_to_disk, push_to_hub=args.push_to_hub)
    else:
        create_train_data_for_sft_not_separated(train_data_path=train_data_path, full_hf_dataset_name=full_hf_dataset_name, save_to_disk=args.save_to_disk, push_to_hub=args.push_to_hub)


if __name__ == "__main__":
    main()