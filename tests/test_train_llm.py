import json

import pytest

import train_llm


def test_format_example_renders_mistral_instruct_template():
    example = {"instruction": "Summarize this.  ", "response": "  A summary.  "}

    result = train_llm.format_example(example)

    assert result == {"text": "<s>[INST] Summarize this. [/INST] A summary.</s>"}


def test_load_training_dataset_missing_file_raises_helpful_error(tmp_path):
    missing_path = str(tmp_path / "does_not_exist.jsonl")

    with pytest.raises(FileNotFoundError, match="No training data found"):
        train_llm.load_training_dataset(missing_path)


def test_load_training_dataset_missing_fields_raises_value_error(tmp_path):
    data_path = tmp_path / "bad.jsonl"
    data_path.write_text(json.dumps({"transcript": "no instruction/response here"}) + "\n")

    with pytest.raises(ValueError, match="missing required field"):
        train_llm.load_training_dataset(str(data_path))


def test_load_training_dataset_loads_valid_pairs(tmp_path):
    data_path = tmp_path / "good.jsonl"
    examples = [
        {"instruction": "Summarize session 1.", "response": "The party found a dragon."},
        {"instruction": "Summarize session 2.", "response": "The party fought a dragon."},
    ]
    data_path.write_text("\n".join(json.dumps(e) for e in examples) + "\n")

    dataset = train_llm.load_training_dataset(str(data_path))

    assert len(dataset) == 2
    assert dataset[0]["instruction"] == "Summarize session 1."
    assert dataset[1]["response"] == "The party fought a dragon."
