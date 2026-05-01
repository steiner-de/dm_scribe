import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vector_db import HashingEmbeddingProvider, VectorDB


def db_path():
    path = Path(__file__).resolve().parents[1] / ".pytest_tmp" / uuid4().hex
    path.parent.mkdir(exist_ok=True)
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
