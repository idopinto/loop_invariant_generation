import torch
import wandb
from transformers import AutoModelForCausalLM, AutoTokenizer, Mxfp4Config
from peft import get_peft_model, LoraConfig
from datasets import load_dataset
from trl import SFTConfig, SFTTrainer

wandb.login()

wandb.init(
    project="rlinv-sft",
    name="gpt-oss-20b-rlinv-sft-test",
)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device {device}.")

def train_sft(model_name: str, dataset_name: str, lora_config: LoraConfig, training_args: SFTConfig):
    dataset = load_dataset(dataset_name, split="train")
    print(f"Loaded dataset {dataset_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    print(f"Loaded tokenizer {tokenizer}...")
    quantization_config = Mxfp4Config(dequantize=True)
    model_kwargs = dict(
        attn_implementation="eager",
        dtype=torch.bfloat16,
        quantization_config=quantization_config,
        use_cache=False,
        device_map="auto",
    )
    model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
    peft_model = get_peft_model(model, lora_config)
    peft_model.print_trainable_parameters()
    trainer = SFTTrainer(
        model=peft_model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
    )
    trainer.train()
    

def main():
    model_name = "openai/gpt-oss-20b"
    trained_model_name = "gpt-oss-20b-rlinv-sft"
    dataset_name = "idopinto/rlinv_train_sft_test"
    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules="all-linear",
        target_parameters=[
            "7.mlp.experts.gate_up_proj",
            "7.mlp.experts.down_proj",
            "15.mlp.experts.gate_up_proj",
            "15.mlp.experts.down_proj",
            "23.mlp.experts.gate_up_proj",
            "23.mlp.experts.down_proj",
        ],
    )
    training_args = SFTConfig(
        learning_rate=2e-4,
        gradient_checkpointing=True,
        num_train_epochs=1,
        logging_steps=1,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine_with_min_lr",
        lr_scheduler_kwargs={"min_lr_rate": 0.1},
        output_dir=trained_model_name,
        report_to="wandb",
        push_to_hub=True,
    )
    train_sft(model_name, dataset_name, lora_config, training_args)