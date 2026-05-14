import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vector_db import HashingEmbeddingProvider, NomicEmbeddingProvider, VectorDB


def db_path():
    path = Path(os.environ["TEMP"]) / "dm_scribe_chroma_tests" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_search_returns_most_relevant_record():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))

    db.add_text("The silver dragon guards the moon temple.", {"kind": "lore"})
    db.add_text("The party buys rope and rations.", {"kind": "inventory"})

    results = db.search("dragon temple", limit=1)

    assert results[0].record.text == "The silver dragon guards the moon temple."
    assert results[0].score > 0


def test_records_persist_to_disk():
    path = db_path()
    db = VectorDB(path, embedder=HashingEmbeddingProvider(dimensions=32))
    db.add_text("The city of Arven fell during the eclipse.", {"kind": "lore"})

    reloaded = VectorDB(path, embedder=HashingEmbeddingProvider(dimensions=32))

    assert len(reloaded.records) == 1
    assert reloaded.records[0].metadata["kind"] == "lore"


def test_search_can_filter_by_metadata():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    db.add_text("The artifact opens the obsidian gate.", {"kind": "lore"})
    db.add_text("The artifact weighs three pounds.", {"kind": "inventory"})

    results = db.search("artifact", metadata_filter={"kind": "inventory"})

    assert len(results) == 1
    assert results[0].record.metadata["kind"] == "inventory"


def test_search_returns_empty_for_blank_query():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    db.add_text("The silver dragon guards the moon temple.", {"kind": "lore"})

    assert db.search("   ") == []


def test_search_rejects_unsupported_metadata_filter():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    db.add_text("The artifact opens the obsidian gate.", {"kind": "lore"})

    with pytest.raises(ValueError, match="Unsupported metadata filter"):
        db.search("artifact", metadata_filter={"campaign_id": "campaign-1"})


def test_vector_db_uses_document_and_query_embedding_modes():
    embedder = RecordingEmbeddingProvider()
    db = VectorDB(db_path(), embedder=embedder)

    db.add_text("The silver dragon guards the moon temple.", {"kind": "lore"})
    db.search("dragon temple")

    assert embedder.input_types == ["document", "query"]


def test_nomic_embedding_provider_defaults_to_current_local_model():
    embedder = NomicEmbeddingProvider()

    assert embedder.model_name == "nomic-ai/nomic-embed-text-v1.5"
    assert embedder.tokenizer_name == "bert-base-uncased"
    assert embedder.max_length == 8192
    assert embedder.dimensions == 768


def test_nomic_embedding_provider_uses_expected_model_load_options(monkeypatch):
    calls = {}

    class FakeTokenizer:
        @staticmethod
        def from_pretrained(name, **kwargs):
            calls["tokenizer"] = (name, kwargs)
            return object()

    class FakeModel:
        def to(self, device):
            calls["device"] = device
            return self

        def eval(self):
            calls["eval"] = True

    class FakeAutoModel:
        @staticmethod
        def from_pretrained(name, **kwargs):
            calls["model"] = (name, kwargs)
            return FakeModel()

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoModel=FakeAutoModel, AutoTokenizer=FakeTokenizer),
    )

    embedder = NomicEmbeddingProvider(device="cpu", max_length=8192)
    embedder._load_model()

    assert calls["tokenizer"] == ("bert-base-uncased", {"model_max_length": 8192})
    assert calls["model"] == (
        "nomic-ai/nomic-embed-text-v1.5",
        {"trust_remote_code": True, "rotary_scaling_factor": 2.0},
    )
    assert calls["device"] == "cpu"
    assert calls["eval"] is True


def test_nomic_embedding_provider_validates_dimensions():
    with pytest.raises(ValueError, match="dimensions"):
        NomicEmbeddingProvider(dimensions=0)

    with pytest.raises(ValueError, match="dimensions"):
        NomicEmbeddingProvider(dimensions=769)


class RecordingEmbeddingProvider:
    def __init__(self):
        self.input_types = []

    def embed(self, text, *, input_type="document"):
        self.input_types.append(input_type)
        return HashingEmbeddingProvider(dimensions=64).embed(text)
