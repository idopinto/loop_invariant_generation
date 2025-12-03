import torch
import os
from pathlib import Path

# Fix memory fragmentation
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"

from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from peft import get_peft_model, LoraConfig
from datasets import load_dataset
from datasets import Dataset
from trl import SFTConfig, SFTTrainer
from typing import List
import logging
from transformers import Mxfp4Config
import wandb
import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config


def parse_dtype(dtype_str: str) -> torch.dtype:
    """Convert string dtype to torch dtype. Defaults to bfloat16."""
    dtype_map = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    return dtype_map.get(dtype_str, torch.bfloat16)


def init_wandb(wandb_project: str):
    wandb.init(project=wandb_project)
    
def load_data(dataset_name: str, limit: int = -1)->Dataset:
    dataset = load_dataset(dataset_name, split="train")
    if limit > 0:
        dataset = dataset.select(range(limit))
    logger.info(f"Loaded dataset {dataset_name}...")
    logger.info(f"Dataset Size: {len(dataset)}")

    return dataset

def init_tokenizer(model_name: str)->AutoTokenizer:
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    logger.info(f"Loaded tokenizer {tokenizer.name_or_path}...")
    return tokenizer

def preview_conversation(tokenizer: AutoTokenizer, messages: List[dict])->None:
    # if not torch.distributed.is_initialized() or torch.distributed.get_rank() == 0:
    conversation = tokenizer.apply_chat_template(messages, tokenize=False)
    print(conversation)

def load_model(model_name: str, model_kwargs: dict)->AutoModelForCausalLM:
    model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
    logger.info(f"Loaded model\n{model}\n...with kwargs\n{model_kwargs}\n")
    return model

def run_inference(tokenizer: AutoTokenizer, model: AutoModelForCausalLM, messages: List[dict], max_new_tokens: int = 512)->None:
    # if not torch.distributed.is_initialized() or torch.distributed.get_rank() == 0:
    messages = [{
        "role": "system",
        "content": messages[0]["content"],
    },
    {
        "role": "user",
        "content": messages[1]["content"],
    }
    ]
    input_ids = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        output_ids = model.generate(input_ids, max_new_tokens=max_new_tokens)
    response = tokenizer.batch_decode(output_ids)[0]
    print("=== Inference Test ===")
    print(response)
    print("="*50)
    return response

def apply_lora(model: AutoModelForCausalLM, lora_config: LoraConfig)->AutoModelForCausalLM:
    peft_model = get_peft_model(model, lora_config)
    if not torch.distributed.is_initialized() or torch.distributed.get_rank() == 0:
        peft_model.print_trainable_parameters()
    return peft_model


def save_model(trainer: SFTTrainer, output_dir: str)->None:
    # if not torch.distributed.is_initialized() or torch.distributed.get_rank() == 0:
    trainer.save_model(output_dir)
    logger.info(f"Saved model to {output_dir}...")
    try:
        trainer.push_to_hub(f"idopinto/{output_dir}")
        logger.info("Pushed model to Hugging Face hub...")

    except Exception as e:
        logger.error(f"Error pushing model to Hugging Face hub: {e}")

def train(tokenizer: AutoTokenizer, peft_model: AutoModelForCausalLM, training_args: SFTConfig, dataset: Dataset)->SFTTrainer:
    trainer = SFTTrainer(
        model=peft_model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
        # max_seq_length is handled by training_args.max_length instead
    )
    trainer.train()
    save_model(trainer, training_args.output_dir)


def evaluate(output_dir: str, model_name: str, messages: List[dict], model_eval_config: dict, base_kwargs: dict)->None:
    """ Load the merged model and evaluate (only on main process)"""
    # if torch.distributed.is_initialized() and torch.distributed.get_rank() != 0:
        # return
    logger.info(f"Evaluating model from {output_dir}...")
    try:
        tokenizer = init_tokenizer(model_name)
        model = load_model(model_name, base_kwargs)
        model = PeftModel.from_pretrained(model, output_dir)
        model = model.merge_and_unload()
        messages = [
            {
                "role": "system",
                "content": messages[0]["content"],
            },
            {
                "role": "user",
                "content": messages[1]["content"],
            },
        ]
        
        input_ids = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            output_ids = model.generate(input_ids, **model_eval_config)
            response = tokenizer.batch_decode(output_ids)[0]

        print("=== Evaluation Results ===")
        print(f"{response}")
        print(f"Response length: {output_ids.shape[1]} tokens")
        print("="*50)
        return response
    except Exception as e:
        logger.error(f"Error evaluating model: {e}")


def main():
    # Load config from YAML
    project_root = Path(__file__).resolve().parent.parent.parent
    logger.info(f" Project root is at {project_root}")
    config_path = project_root / "configs" / "train_sft_config.yaml"
    logger.info(f" Config path is at {config_path}. Loading..")
    config = load_config(config_path)
    
    # init_wandb(config["wandb_project"])
    
    # Extract top-level config
    model_name = config["model_name"]
    hf_dataset = config["hf_dataset"]    
    output_dir = config["sft_config"]["output_dir"]
    logger.info(f"model_name: {model_name} | hf_dataset: {hf_dataset} | output_dir: {output_dir}")
    # Build LoRA config from YAML
    lora_config = LoraConfig(**config["lora_config"])
    # logger.info(f"LoRA config: {lora_config}")
    # Build SFT training args from YAML
    training_args = SFTConfig(**config["sft_config"])
    # logger.info(f"Training args: {training_args}")
    # Build model kwargs from YAML
    model_kwargs = dict(
        attn_implementation=config["model_train_config"]["attn_implementation"],
        dtype=parse_dtype(config["model_train_config"]["dtype"]),
        quantization_config=Mxfp4Config(dequantize=True),
        use_cache=config["model_train_config"]["use_cache"],
        device_map=config["model_train_config"]["device_map"],
    )
    # logger.info(f"Model kwargs: {model_kwargs}")
    
    dataset = load_data(hf_dataset, limit=config["limit"])
    tokenizer = init_tokenizer(model_name)
    model = load_model(model_name, model_kwargs)
    peft_model = apply_lora(model, lora_config)
    # train(tokenizer, peft_model, training_args, dataset)
    evaluate(output_dir, model_name, dataset[0]["messages"], config["model_eval_config"], config["model_train_config"])
    wandb.finish()
    logger.info("DONE.")

if __name__ == "__main__":
    main()