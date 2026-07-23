# D&D Lore LLM Training Guide

## Overview
This guide outlines how to build and fine-tune a custom Large Language Model (LLM) specialized for your homebrewed D&D world. Since training an LLM from scratch requires massive resources (data, compute, time), we'll focus on **fine-tuning an existing open-source model** using your custom D&D content.

## Prerequisites
- Python 3.11+ (matches the bot's requirement)
- GPU with at least 8GB VRAM (NVIDIA recommended for efficiency)
- 50GB+ free disk space
- Access to D&D materials (rulebooks, homebrew docs, campaign notes)

## Step 1: Choose a Base Model
Select an open-source LLM to fine-tune:
- **Llama 2 (7B or 13B)**: Strong general capabilities, good for creative writing. Requires Meta's license.
- **Mistral 7B**: Excellent performance, efficient, and permissive license.
- **Phi-2 (2.7B)**: Smaller, faster, good for focused domains like D&D.
- **Gemma 7B**: Google's model, good balance of size and capability.

Download from Hugging Face: https://huggingface.co/

## Step 2: Collect Training Data

The bot builds this for you automatically. Every time `/stop` finishes a session, it
saves the transcript + LLM summary as a training example in `training_data/`
(see `utils.save_transcript_for_training`). Once you've run a handful of real
sessions, turn that into a fine-tuning dataset with:

```bash
# as a bot admin, in Discord:
/export_data

# or locally:
python -c "from utils import export_training_data; export_training_data()"
```

This writes `exported_training_data.jsonl`, one instruction/response pair per
session, in the format `train_llm.py` expects:

```json
{"instruction": "Summarize the following D&D session transcript. Focus on...\n\nTranscript: [00:03] Elric: I cast fireball...", "response": "The party stormed the goblin camp..."}
```

Records saved before this pipeline existed (transcript only, no summary) are
skipped automatically. Because the "response" side is itself LLM-generated,
this alone mostly teaches the model to imitate its own summarization style
(self-distillation) — not new D&D knowledge. For real lore/rules knowledge,
supplement `exported_training_data.jsonl` with hand-authored instruction/response
pairs (homebrew lore, rulebook Q&A, campaign notes) in the same JSON Lines format,
and consider hand-editing some of the auto-collected summaries for quality before
training on them. Aim for quality over volume — even a few hundred good pairs
beats thousands of noisy ones for LoRA fine-tuning.

## Step 3: Fine-Tuning Process

Use the scripts in this repo — `train_llm.py` fine-tunes with LoRA/QLoRA via
Hugging Face `peft`/`trl`, which needs far less VRAM than full fine-tuning.

1. Install the training extras (not needed to run the bot itself):
   ```bash
   uv sync --extra train
   ```
2. Run training:
   ```bash
   python src/train_llm.py --data exported_training_data.jsonl --output-dir models/dnd-llm
   ```
   Defaults to `mistralai/Mistral-7B-Instruct-v0.3` in 4-bit (QLoRA). Override with
   `--base-model`, and see `python src/train_llm.py --help` for the rest
   (epochs, batch size, learning rate, `--no-4bit` for higher-fidelity training
   on a bigger GPU).
3. This needs a CUDA GPU. If you don't have one locally, use Google Colab Pro,
   RunPod, or AWS SageMaker, then copy `models/dnd-llm/` back down.

## Step 4: Evaluation and Iteration
- Test the model on D&D-specific prompts
- Evaluate coherence, factual accuracy, and creativity
- Iterate by adding more data or adjusting hyperparameters

## Step 5: Integration with Discord Bot

Package the fine-tuned adapter for Ollama (the bot already talks to Ollama for
summarization, so this is a drop-in swap, not a new integration):

```bash
python src/package_for_ollama.py --base-model mistralai/Mistral-7B-Instruct-v0.3 \
    --adapter-dir models/dnd-llm --model-name dnd-scribe
```

This merges the LoRA adapter into the base model and prints the remaining
steps (GGUF conversion via llama.cpp, then `ollama create`). Once the model
exists in Ollama, point the bot at it by setting in `.env`:

```
OLLAMA_MODEL=dnd-scribe
```

`transcriber.summarize_with_llm` reads this at runtime — no code changes needed.

## Hardware Requirements
- **Minimum**: 16GB RAM, 4GB GPU VRAM (slow training)
- **Recommended**: 32GB RAM, 24GB GPU VRAM (RTX 3090/4090)
- **Cloud Option**: Use Google Colab Pro, AWS SageMaker, or RunPod for GPU access

## Challenges and Tips
- **Overfitting**: Monitor for model becoming too specific to your data
- **Hallucinations**: D&D models may invent lore; validate outputs
- **Compute Cost**: Fine-tuning can take 4-24 hours depending on setup
- **Legal**: Ensure your training data doesn't violate copyrights

## Resources
- Hugging Face Docs: https://huggingface.co/docs
- D&D Datasets: Search for "D&D text datasets" on Hugging Face
- Community: r/LocalLLaMA, r/MachineLearning