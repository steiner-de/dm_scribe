import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory_bank import MemoryBank, SessionNotes
from vector_db import HashingEmbeddingProvider, VectorDB


def db_path():
    path = Path(__file__).resolve().parents[1] / ".pytest_tmp" / uuid4().hex
    path.parent.mkdir(exist_ok=True)
    return path


class StubNotesGenerator:
    def generate_notes(self, transcript, session_id):
        return SessionNotes(
            session_id=session_id,
            summary="The party found the crown beneath the city.",
            notable_events=["The party found the crown."],
            lore_entries=["The crown belongs to the old city faction."],
        )


def test_remember_transcript_stores_transcript_summary_and_lore():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    bank = MemoryBank(db, notes_generator=StubNotesGenerator())

    notes = bank.remember_transcript(
        "The party found the crown beneath the city.",
        session_id="session-1",
        channel_name="table-one",
    )

    kinds = {record.metadata["kind"] for record in db.records}
    assert notes.summary == "The party found the crown beneath the city."
    assert kinds == {"transcript", "session_summary", "lore"}


def test_search_lore_only_returns_lore_records():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    bank = MemoryBank(db, notes_generator=StubNotesGenerator())
    bank.remember_transcript("The party found the crown.", session_id="session-1")

    results = bank.search_lore("crown")

    assert len(results) == 1
    assert results[0].record.metadata["kind"] == "lore"


def test_search_session_only_returns_matching_session_records():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    bank = MemoryBank(db, notes_generator=StubNotesGenerator())
    bank.remember_transcript("The party found the crown.", session_id="session-1")
    bank.remember_transcript("The party found the crown.", session_id="session-2")

    results = bank.search_session("crown", session_id="session-2")

    assert results
    assert {result.record.metadata["session_id"] for result in results} == {"session-2"}
