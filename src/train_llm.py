"""
Training script for fine-tuning a D&D-specific LLM.
"""

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    DataCollatorForLanguageModeling,
)
from datasets import load_dataset


def load_data(data_path):
    """Load and preprocess training data."""
    # Assuming data is in JSON Lines format
    dataset = load_dataset("json", data_files=data_path)
    return dataset


def tokenize_function(examples, tokenizer):
    """Tokenize the data."""
    return tokenizer(examples["text"], truncation=True, padding="max_length", max_length=512)


def main():
    # Configuration
    model_name = "microsoft/DialoGPT-medium"  # Or your chosen base model
    data_path = "./data/dnd_training_data.jsonl"
    output_dir = "./models/dnd-llm"

    # Load model and tokenizer
    model = AutoModelForCausalLM.from_pretrained(model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Add padding token if needed
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load and preprocess data
    dataset = load_data(data_path)
    tokenized_dataset = dataset.map(
        lambda x: tokenize_function(x, tokenizer),
        batched=True,
        remove_columns=dataset["train"].column_names,
    )

    # Data collator
    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        overwrite_output_dir=True,
        num_train_epochs=3,
        per_device_train_batch_size=4,
        save_steps=500,
        save_total_limit=2,
        logging_steps=100,
        learning_rate=5e-5,
        weight_decay=0.01,
        warmup_steps=500,
        fp16=True,  # Use mixed precision if GPU supports
    )

    # Trainer
    trainer = TrainingArguments(
        model=model,
        args=training_args,
        data_collator=data_collator,
        train_dataset=tokenized_dataset["train"],
    )

    # Train
    trainer.train()

    # Save model
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    print(f"Model saved to {output_dir}")


if __name__ == "__main__":
    main()
