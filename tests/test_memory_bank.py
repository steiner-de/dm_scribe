import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory_bank import (
    CHARACTER,
    DM_ONLY,
    NO_MEMORY_FOUND,
    NO_SESSION_RECAP_FOUND,
    PUBLIC,
    MemoryBank,
    SessionNotes,
    format_memory_results,
    normalize_visibility,
)
from vector_db import HashingEmbeddingProvider, SearchResult, VectorDB, VectorRecord


def db_path():
    path = Path(os.environ["TEMP"]) / "dm_scribe_chroma_tests" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


class StubNotesGenerator:
    def generate_notes(self, transcript, session_id):
        return SessionNotes(
            session_id=session_id,
            summary="The party found the crown beneath the city.",
            notable_events=["The party found the crown."],
            lore_entries=["The crown belongs to the old city faction."],
        )


class FakeVectorDB:
    def __init__(self):
        self.records = []

    def add_text(self, text, metadata=None, record_id=None):
        record = VectorRecord(
            id=record_id or str(len(self.records)),
            text=text,
            metadata=metadata or {},
            embedding=[],
        )
        self.records.append(record)
        return record

    def add_many(self, entries):
        return [self.add_text(text, metadata) for text, metadata in entries if text.strip()]

    def search(self, query, limit=5, metadata_filter=None):
        terms = query.lower().split()
        matches = []
        for record in self.records:
            if metadata_filter and any(
                record.metadata.get(key) != value for key, value in metadata_filter.items()
            ):
                continue
            if terms and not any(term in record.text.lower() for term in terms):
                continue
            matches.append(SearchResult(record=record, score=1.0))
        return matches[:limit]


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
    assert {record.metadata["visibility"] for record in db.records} == {PUBLIC}


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
        visibility=CHARACTER,
        owner_user_id="alice",
    )

    assert record.metadata["kind"] == "note"
    assert record.metadata["guild"] == "home-table"
    assert record.metadata["note_path"] == "Campaign/Session 1.md"
    assert record.metadata["summary_text"] == "The party found the crown."
    assert record.metadata["visibility"] == CHARACTER
    assert record.metadata["owner_user_id"] == "alice"


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


def test_search_accessible_respects_visibility_and_guild():
    db = FakeVectorDB()
    bank = MemoryBank(db, notes_generator=StubNotesGenerator())
    bank.remember_note(
        "The crown is public lore.",
        session_id="session-1",
        summary_text="public",
        guild="home-table",
        visibility=PUBLIC,
    )
    bank.remember_note(
        "Alice carries the crown.",
        session_id="session-1",
        summary_text="character",
        guild="home-table",
        visibility=CHARACTER,
        owner_user_id="alice",
    )
    bank.remember_note(
        "The crown is cursed in the DM notes.",
        session_id="session-1",
        summary_text="dm",
        guild="home-table",
        visibility=DM_ONLY,
    )
    bank.remember_note(
        "The crown belongs to another table.",
        session_id="session-1",
        summary_text="other",
        guild="away-table",
        visibility=PUBLIC,
    )

    bob_results = bank.search_accessible("crown", user_id="bob", guild="home-table")
    alice_results = bank.search_accessible("crown", user_id="alice", guild="home-table")
    dm_results = bank.search_accessible(
        "crown",
        user_id="dm",
        dm_access=True,
        guild="home-table",
    )

    assert [result.record.text for result in bob_results] == ["The crown is public lore."]
    assert {result.record.text for result in alice_results} == {
        "The crown is public lore.",
        "Alice carries the crown.",
    }
    assert {result.record.text for result in dm_results} == {
        "The crown is public lore.",
        "Alice carries the crown.",
        "The crown is cursed in the DM notes.",
    }


def test_last_session_recap_uses_latest_session_summary_and_lore():
    db = FakeVectorDB()
    bank = MemoryBank(db, notes_generator=StubNotesGenerator())
    db.add_text(
        "The party entered the old city.",
        {
            "kind": "session_summary",
            "session_id": "session-1",
            "guild": "home-table",
            "session_date": "2026-05-01",
            "visibility": PUBLIC,
        },
    )
    db.add_text(
        "The party recovered the silver crown.",
        {
            "kind": "session_summary",
            "session_id": "session-2",
            "guild": "home-table",
            "session_date": "2026-05-08",
            "visibility": PUBLIC,
        },
    )
    db.add_text(
        "The crown belongs to the old city faction.",
        {
            "kind": "lore",
            "session_id": "session-2",
            "guild": "home-table",
            "session_date": "2026-05-08",
            "visibility": PUBLIC,
        },
    )
    db.add_text(
        "The crown is cursed.",
        {
            "kind": "lore",
            "session_id": "session-2",
            "guild": "home-table",
            "session_date": "2026-05-08",
            "visibility": DM_ONLY,
        },
    )
    db.add_text(
        "Another table found a different crown.",
        {
            "kind": "session_summary",
            "session_id": "session-3",
            "guild": "away-table",
            "session_date": "2026-05-15",
            "visibility": PUBLIC,
        },
    )

    player_recap = bank.last_session_recap(guild="home-table", user_id="alice")
    dm_recap = bank.last_session_recap(
        guild="home-table",
        user_id="dm",
        dm_access=True,
    )

    assert "2026-05-08" in player_recap
    assert "The party recovered the silver crown." in player_recap
    assert "The crown belongs to the old city faction." in player_recap
    assert "The party entered the old city." not in player_recap
    assert "Another table" not in player_recap
    assert "The crown is cursed." not in player_recap
    assert "The crown is cursed." in dm_recap


def test_last_session_recap_returns_empty_message_without_summary():
    bank = MemoryBank(FakeVectorDB(), notes_generator=StubNotesGenerator())

    assert bank.last_session_recap(guild="home-table", user_id="alice") == NO_SESSION_RECAP_FOUND


def test_normalize_visibility_accepts_only_known_memory_scopes():
    assert normalize_visibility(None) == PUBLIC
    assert normalize_visibility(" Character ") == CHARACTER
    assert normalize_visibility("DM") == DM_ONLY
    assert normalize_visibility("secret") is None


def test_format_memory_results_is_discord_friendly():
    assert format_memory_results([]) == NO_MEMORY_FOUND

    result = SearchResult(
        record=VectorRecord(
            id="1",
            text="The   crown\nbelongs to Alice.",
            metadata={
                "session_date": "2026-05-13",
                "kind": "note",
                "note_path": "Campaign/Session 1.md",
            },
            embedding=[],
        ),
        score=1.0,
    )

    message = format_memory_results([result])

    assert "**2026-05-13 | note | Campaign/Session 1.md**" in message
    assert "The crown belongs to Alice." in message
