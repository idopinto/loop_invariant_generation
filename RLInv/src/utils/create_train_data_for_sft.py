import json
from pathlib import Path
from datasets import Dataset
from datasets import load_dataset
from tqdm import tqdm
DATA_DIR = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/dataset/training")

def create_train_data_for_sft(train_data_path: Path, hf_dataset_name: str, save_to_disk: bool = False, push_to_hub: bool = False) -> list:
    system_prompt = "You understand C programs well and can generate strong loop invariants for program verification."
    user_prompt_template = """Given the following C program, generate only one loop invariant after line {line_number}.
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

    samples = []
    for data_point in tqdm(train_data):
        for invariant in tqdm(data_point["invariants"]):
            sample ={"messages":[
                {"role": "system", "content": system_prompt, "thinking": None},
                {"role": "user", "content": user_prompt_template.format(
                    formatted_program=data_point["rf_program"], 
                    line_number=invariant["line"]
                ), "thinking": None},
                {"role": "assistant", "content": f"assert({invariant['invariant']});", "thinking": None}
            ]
            }
            samples.append(sample)

    hf_dataset = Dataset.from_list(samples)
    if save_to_disk:
        hf_data_dir = DATA_DIR / "hf_datasets"
        hf_data_dir.mkdir(parents=True, exist_ok=True)
        hf_dataset.save_to_disk(hf_data_dir / hf_dataset_name)
    if push_to_hub:
        hf_dataset.push_to_hub(hf_dataset_name)
    return hf_dataset


def load_train_data_for_sft(hf_dataset_name: str, split: str = "train", load_from_disk: bool = False) -> Dataset:
    if load_from_disk:
        hf_data_dir = DATA_DIR / "hf_datasets"
        hf_data_dir.mkdir(parents=True, exist_ok=True)
        return Dataset.load_from_disk(hf_data_dir / hf_dataset_name)
    else:
        return load_dataset(hf_dataset_name, split=split)


def main():
    train_data_path = DATA_DIR / "example_train.json"
    hf_dataset_name = "idopinto/rlinv_train_sft_test"
    save_to_disk = True
    push_to_hub = True
    create_train_data_for_sft(train_data_path, hf_dataset_name, save_to_disk, push_to_hub)
    load_from_disk = True
    dataset = load_train_data_for_sft(hf_dataset_name, split="train", load_from_disk=load_from_disk)
    print("Loaded dataset:")
    print(dataset[0])

if __name__ == "__main__":
    main()