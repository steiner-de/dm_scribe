"""
LoRA fine-tuning script for a D&D-specialized version of the summarization LLM.

Requires real training data and a CUDA GPU with enough VRAM for the base
model in 4-bit (QLoRA) -- neither is available in every environment this
repo is developed in. Heavy ML imports are deferred into main() so that
`python src/train_llm.py --help` and the pure data-loading helpers stay
usable (and testable) without peft/bitsandbytes installed.

Usage:
    # 1. Collect a few real sessions with the bot (each /stop call saves a
    #    transcript+summary pair to training_data/), then build the dataset:
    python -c "from utils import export_training_data; export_training_data()"

    # 2. Install the training extras (not needed to run the bot itself):
    uv sync --extra train

    # 3. Fine-tune:
    python src/train_llm.py --data exported_training_data.jsonl --output-dir models/dnd-llm

    # 4. Package the resulting adapter for Ollama:
    python src/package_for_ollama.py --base-model <same as --base-model above> \\
        --adapter-dir models/dnd-llm

See DND_LLM_GUIDE.md for the full walkthrough, including cloud GPU options
(Colab/RunPod) if no local GPU is available.
"""

import argparse
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_BASE_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
DEFAULT_DATA_PATH = "exported_training_data.jsonl"
DEFAULT_OUTPUT_DIR = "models/dnd-llm"

# Mistral's instruction-tuned chat format.
PROMPT_TEMPLATE = "<s>[INST] {instruction} [/INST] {response}</s>"


def format_example(example):
    """Render one instruction/response pair into the base model's chat format."""
    return {
        "text": PROMPT_TEMPLATE.format(
            instruction=example["instruction"].strip(),
            response=example["response"].strip(),
        )
    }


def load_training_dataset(data_path):
    """
    Load instruction/response pairs produced by utils.export_training_data().

    Each line must be a JSON object with "instruction" and "response" keys.
    """
    from datasets import load_dataset

    if not os.path.exists(data_path):
        raise FileNotFoundError(
            f"No training data found at '{data_path}'. Run a few sessions with the bot "
            "first, then generate it with: "
            'python -c "from utils import export_training_data; export_training_data()"'
        )

    dataset = load_dataset("json", data_files=data_path, split="train")
    missing = [key for key in ("instruction", "response") if key not in dataset.column_names]
    if missing:
        raise ValueError(
            f"Training data at '{data_path}' is missing required field(s): {missing}. "
            "Each line must have 'instruction' and 'response' keys."
        )
    return dataset


def build_lora_config():
    from peft import LoraConfig

    return LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune a local D&D LLM with LoRA/QLoRA.")
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--data", default=DEFAULT_DATA_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument(
        "--no-4bit",
        action="store_true",
        help="Disable 4-bit quantization (needs ~4x more VRAM, higher fidelity).",
    )
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    dataset = load_training_dataset(args.data)
    logger.info(f"Loaded {len(dataset)} training example(s) from {args.data}")

    import torch
    from peft import get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainingArguments,
    )
    from trl import SFTTrainer

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quantization_config = None
    if not args.no_4bit:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=quantization_config,
        device_map="auto",
    )
    if quantization_config is not None:
        model = prepare_model_for_kbit_training(model)

    model = get_peft_model(model, build_lora_config())
    model.print_trainable_parameters()

    dataset = dataset.map(format_example)

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        overwrite_output_dir=True,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        logging_steps=10,
        save_steps=100,
        save_total_limit=2,
        bf16=torch.cuda.is_available(),
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        dataset_text_field="text",
        tokenizer=tokenizer,
        max_seq_length=args.max_seq_length,
    )

    trainer.train()

    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    logger.info(f"LoRA adapter saved to {args.output_dir}")
    logger.info(
        "Next: merge the adapter and package it for Ollama with "
        f"`python src/package_for_ollama.py --base-model {args.base_model} "
        f"--adapter-dir {args.output_dir}`"
    )


if __name__ == "__main__":
    main()
