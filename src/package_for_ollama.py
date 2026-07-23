"""
Merge a LoRA adapter produced by train_llm.py into its base model and
prepare it for import into Ollama, so the fine-tuned D&D model can replace
stock "mistral" in transcriber.py (via the OLLAMA_MODEL env var).

This script does NOT perform GGUF conversion -- that requires llama.cpp,
which is not a project dependency, since its API/scripts change across
versions. It merges the adapter and writes an Ollama Modelfile, then prints
the exact remaining commands to run.

Usage:
    python src/package_for_ollama.py \\
        --base-model mistralai/Mistral-7B-Instruct-v0.3 \\
        --adapter-dir models/dnd-llm \\
        --model-name dnd-scribe
"""

import argparse
import os

MODELFILE_TEMPLATE = """FROM {gguf_path}

SYSTEM \"\"\"You are a Dungeon Master's assistant. You summarize D&D session \
transcripts into concise, well-organized notes covering key events, lore, \
loot, and character decisions.\"\"\"

PARAMETER temperature 0.7
"""


def merge_adapter(base_model, adapter_dir, merged_dir):
    """Merge a LoRA adapter into its base model and save the merged weights."""
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model = AutoModelForCausalLM.from_pretrained(base_model, device_map="auto")
    model = PeftModel.from_pretrained(model, adapter_dir)
    model = model.merge_and_unload()

    os.makedirs(merged_dir, exist_ok=True)
    model.save_pretrained(merged_dir)
    AutoTokenizer.from_pretrained(base_model).save_pretrained(merged_dir)
    return merged_dir


def write_modelfile(gguf_path, modelfile_path):
    os.makedirs(os.path.dirname(modelfile_path) or ".", exist_ok=True)
    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(MODELFILE_TEMPLATE.format(gguf_path=gguf_path))
    return modelfile_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Merge a LoRA adapter and prepare it for Ollama import."
    )
    parser.add_argument("--base-model", required=True, help="Same base model used in train_llm.py")
    parser.add_argument("--adapter-dir", required=True, help="Output dir from train_llm.py")
    parser.add_argument("--merged-dir", default="models/dnd-llm-merged")
    parser.add_argument("--model-name", default="dnd-scribe")
    return parser.parse_args()


def main():
    args = parse_args()

    merged_dir = merge_adapter(args.base_model, args.adapter_dir, args.merged_dir)

    gguf_path = os.path.join(merged_dir, f"{args.model_name}.gguf")
    modelfile_path = os.path.join(merged_dir, "Modelfile")
    write_modelfile(gguf_path, modelfile_path)

    print(f"Merged model saved to: {merged_dir}")
    print()
    print("Remaining steps:")
    print("  1. Convert the merged model to GGUF with llama.cpp:")
    print(f"       python convert_hf_to_gguf.py {merged_dir} --outfile {gguf_path}")
    print("  2. Create the Ollama model from it:")
    print(f"       ollama create {args.model_name} -f {modelfile_path}")
    print("  3. Point the bot at it by setting in .env:")
    print(f"       OLLAMA_MODEL={args.model_name}")


if __name__ == "__main__":
    main()
