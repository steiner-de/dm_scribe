# D&D Lore LLM Training Guide

## Overview
This guide outlines how to build and fine-tune a custom Large Language Model (LLM) specialized for your homebrewed D&D world. Since training an LLM from scratch requires massive resources (data, compute, time), we'll focus on **fine-tuning an existing open-source model** using your custom D&D content.

## Prerequisites
- Python 3.13+
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
Gather diverse, high-quality text data specific to your homebrewed D&D world:
- **Core Sources**:
  - Official D&D rulebooks (5e Player's Handbook, DM Guide, Monster Manual)
  - Your homebrew content (custom races, classes, spells, lore, campaign notes)
  - Character backstories and NPC descriptions
- **Additional Data**:
  - Game session transcripts (from your bot's output)
  - Fan-created D&D content (Reddit threads, forums)
  - Related fantasy literature excerpts
- **Data Volume**: Aim for 10,000-100,000+ text samples. Quality > quantity.
- **Format**: JSON Lines format with instruction-response pairs for chat models.

Example data structure:
```json
{"instruction": "Describe the ancient dragon cult in my campaign", "response": "The Cult of the Eternal Flame worships..."}
```

## Step 3: Fine-Tuning Process
Use Hugging Face Transformers ecosystem:

### Option A: Using AutoTrain (Easiest)
1. Install: `pip install autotrain-advanced`
2. Prepare data in CSV/JSON format
3. Run training:
```bash
autotrain llm --train --project_name dnd-llm --model meta-llama/Llama-2-7b-hf --data_path ./data --text_column text --lr 2e-4 --batch_size 4 --epochs 3 --gradient_accumulation 4
```

### Option B: Using Axolotl (Advanced)
1. Install Axolotl: https://github.com/OpenAccess-AI-Collective/axolotl
2. Configure YAML file for your model and data
3. Run training with optimized settings

### Option C: Custom Script
Use the provided `train_llm.py` script in this repo.

## Step 4: Evaluation and Iteration
- Test the model on D&D-specific prompts
- Evaluate coherence, factual accuracy, and creativity
- Iterate by adding more data or adjusting hyperparameters

## Step 5: Integration with Discord Bot
- Host the model locally using vLLM or Text Generation Inference
- Create API endpoints for summarization and lore generation
- Integrate via HTTP requests from your bot

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