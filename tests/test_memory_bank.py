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
        guild="home-table",
        channel_name="table-one",
        note_path="Campaign/Session 1.md",
        session_date="2026-05-05",
    )

    kinds = {record.metadata["kind"] for record in db.records}
    assert notes.summary == "The party found the crown beneath the city."
    assert kinds == {"transcript", "session_summary", "lore"}
    assert {record.metadata["guild"] for record in db.records} == {"home-table"}
    assert {record.metadata["note_path"] for record in db.records} == {"Campaign/Session 1.md"}
    assert {record.metadata["session_date"] for record in db.records} == {"2026-05-05"}


def test_search_lore_only_returns_lore_records():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    bank = MemoryBank(db, notes_generator=StubNotesGenerator())
    bank.remember_transcript("The party found the crown.", session_id="session-1")

    results = bank.search_lore("crown")

    assert len(results) == 1
    assert results[0].record.metadata["kind"] == "lore"


def test_remember_note_stores_obsidian_note_metadata():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    bank = MemoryBank(db, notes_generator=StubNotesGenerator())

    record = bank.remember_note(
        "The party found the crown beneath the city.",
        session_id="session-1",
        summary_text="The party found the crown.",
        guild="home-table",
        channel_name="table-one",
        note_path="Campaign/Session 1.md",
        session_date="2026-05-05",
    )

    assert record.metadata["kind"] == "note"
    assert record.metadata["guild"] == "home-table"
    assert record.metadata["note_path"] == "Campaign/Session 1.md"
    assert record.metadata["summary_text"] == "The party found the crown."


def test_search_notes_only_returns_note_records():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    bank = MemoryBank(db, notes_generator=StubNotesGenerator())
    bank.remember_transcript("The party found the crown.", session_id="session-1")
    bank.remember_note(
        "The note says the crown belongs to the old city faction.",
        session_id="session-1",
        summary_text="The party found the crown.",
    )

    results = bank.search_notes("crown")

    assert len(results) == 1
    assert results[0].record.metadata["kind"] == "note"


def test_search_session_only_returns_matching_session_records():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    bank = MemoryBank(db, notes_generator=StubNotesGenerator())
    bank.remember_transcript("The party found the crown.", session_id="session-1")
    bank.remember_transcript("The party found the crown.", session_id="session-2")

    results = bank.search_session("crown", session_id="session-2")

    assert results
    assert {result.record.metadata["session_id"] for result in results} == {"session-2"}


def test_build_context_returns_retrieved_snippets():
    db = VectorDB(db_path(), embedder=HashingEmbeddingProvider(dimensions=64))
    bank = MemoryBank(db, notes_generator=StubNotesGenerator())
    bank.remember_note(
        "The note says the crown belongs to the old city faction.",
        session_id="session-1",
        summary_text="The party found the crown.",
        guild="home-table",
        note_path="Campaign/Session 1.md",
        session_date="2026-05-05",
    )

    context = bank.build_context("crown")

    assert "crown" in context
    assert "Campaign/Session 1.md" in context
