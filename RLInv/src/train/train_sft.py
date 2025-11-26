import torch
import os

# Fix memory fragmentation
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_wandb():
    wandb.init(project="rlinv-sft")
    
def load_data()->Dataset:
    dataset_name = "idopinto/rlinv_train_sft_test"
    dataset = load_dataset(dataset_name, split="train")
    logger.info(f"Loaded dataset {dataset_name}...")
    logger.info(f"Dataset length: {len(dataset)}")
    logger.info("="*100)
    return dataset

def init_tokenizer(model_name: str)->AutoTokenizer:
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    logger.info(f"Loaded tokenizer {tokenizer}...")
    return tokenizer

def preview_conversation(tokenizer: AutoTokenizer, messages: List[dict])->None:
    # if not torch.distributed.is_initialized() or torch.distributed.get_rank() == 0:
    conversation = tokenizer.apply_chat_template(messages, tokenize=False)
    print(conversation)

def load_model(model_name: str, model_kwargs: dict)->AutoModelForCausalLM:
    model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
    logger.info(f"Loaded model {model}...")
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


def evaluate(output_dir: str, tokenizer: AutoTokenizer, model: AutoModelForCausalLM, messages: List[dict])->None:
    """ Load the merged model and evaluate (only on main process)"""
    # if torch.distributed.is_initialized() and torch.distributed.get_rank() != 0:
        # return
    logger.info(f"Evaluating model from {output_dir}...")
    base_kwargs = {
        "attn_implementation": "eager",
        "dtype": torch.bfloat16,
        "use_cache": True,
        "device_map": "auto",
    }
    try:
        model = AutoModelForCausalLM.from_pretrained("openai/gpt-oss-20b", **base_kwargs)
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

        gen_kwargs = {
            "max_new_tokens": 512,
            "do_sample": True,
            "temperature": 0.6,
            "top_p": 0.9,
            "pad_token_id": tokenizer.eos_token_id, 
        }
        with torch.inference_mode():
            output_ids = model.generate(input_ids, **gen_kwargs)
            response = tokenizer.batch_decode(output_ids)[0]

        print("=== Evaluation Results ===")
        print(f"{response}")
        logger.info(f"Response length: {output_ids.shape[1]} tokens")
        print("="*50)
        return response
    except Exception as e:
        logger.error(f"Error evaluating model: {e}")


def main():
    init_wandb()
    # project_root = Path(__file__).resolve().parent.parent.parent
    model_name = "openai/gpt-oss-20b"
    output_dir = "gpt-oss-20b-rlinv-sft2"
    dataset_name = "idopinto/rlinv_train_sft_test2"
    # deepspeed_config = project_root / "configs" / "ds_zero3.json"

    print("="*100)
    print(f"model_name: {model_name}")
    print(f"dataset_name: {dataset_name}")
    print(f"output_dir: {output_dir}")
    print("="*100)
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
        lora_dropout=0.0, # Must be 0 when using target_parameters
        bias="none", # Must be "none" when using target_parameters
        task_type="CAUSAL_LM",
    )

    training_args = SFTConfig(
        learning_rate=2e-4,
        gradient_checkpointing=True,
        num_train_epochs=1,
        logging_steps=1,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        max_length=2048,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine_with_min_lr",
        lr_scheduler_kwargs={"min_lr_rate": 0.1},
        output_dir=output_dir,
        report_to="wandb",
        push_to_hub=True,
    )

    model_kwargs = dict(
        attn_implementation="eager",
        dtype=torch.bfloat16,
        quantization_config=Mxfp4Config(dequantize=True), # removed quantizatio_config and device_map for DeepSpeed compatibility
        use_cache=False,
        device_map="auto",
    )
    dataset = load_data()
    tokenizer = init_tokenizer(model_name)
    model = load_model(model_name, model_kwargs)
    peft_model = apply_lora(model, lora_config)
    train(tokenizer, peft_model, training_args, dataset)
    evaluate(output_dir, tokenizer, model, dataset[0]["messages"])
    wandb.finish()
    logger.info("Training finished...")

    
if __name__ == "__main__":
    main()