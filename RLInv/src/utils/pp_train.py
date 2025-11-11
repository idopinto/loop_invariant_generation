from datasets import Dataset  # Commented out - not used yet, was causing hang
from trl import SFTTrainer
from transformers import AutoTokenizer
from pathlib import Path
import json
# Each item in the dataset is one full conversation
program_dir = Path("dataset/training") / "Programs"
invariants_file = Path("dataset/training") / "invariants.json"
with open(invariants_file, "r") as f:
    invariants_data = json.load(f)
system_msg = "You are a helpful assistant and an expert C programmer. You can generate strong loop invariants for C programs."

user_msg = """Generate a strong loop invariant that helps prove the target property of the following C program: 
```c\n{program}\n```

Available locations for placing the invariant:
{locations}

Output Format:
assert(<invariant>); // Line <line_number>
"""

program = (program_dir / "5_2.c").read_text().strip() # type: ignore
locations = [f"Line {ln['line']}" for ln in invariants_data["5_2.c"]]
data = [
    {
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg.format(program=program, locations=locations)},
            {"role": "assistant", "content": f"assert({invariants_data['5_2.c'][0]['invariant']}); // Line {invariants_data['5_2.c'][0]['line']}"}
        ]
    }
]

train_dataset = Dataset.from_list(data)

model = "Qwen/Qwen2-0.5B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model)
trainer = SFTTrainer(
    model=model,
    train_dataset=train_dataset,
    # No 'dataset_text_field' needed!
    # By default, it looks for a "messages" column.
    # If your column is named differently, use:
    # dataset_kwargs={"messages_column": "your_column_name"}
)   
trainer.train()