from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Protocol

from vector_db import Metadata, SearchResult, VectorDB, VectorRecord


@dataclass(frozen=True)
class SessionNotes:
    session_id: str
    summary: str
    notable_events: list[str] = field(default_factory=list)
    lore_entries: list[str] = field(default_factory=list)


class SessionNotesGenerator(Protocol):
    def generate_notes(self, transcript: str, session_id: str) -> SessionNotes:
        ...


class HeuristicSessionNotesGenerator:
    _sentence_pattern = re.compile(r"(?<=[.!?])\s+")

    def generate_notes(self, transcript: str, session_id: str) -> SessionNotes:
        sentences = [
            sentence.strip()
            for sentence in self._sentence_pattern.split(transcript.strip())
            if sentence.strip()
        ]
        summary = " ".join(sentences[:3]) if sentences else transcript.strip()

        return SessionNotes(
            session_id=session_id,
            summary=summary,
            notable_events=sentences[:5],
            lore_entries=self._extract_lore_entries(sentences),
        )

    def _extract_lore_entries(self, sentences: list[str]) -> list[str]:
        lore_keywords = ("lore", "npc", "quest", "city", "kingdom", "god", "artifact", "faction")
        return [
            sentence
            for sentence in sentences
            if any(keyword in sentence.lower() for keyword in lore_keywords)
        ][:10]


class MemoryBank:
    def __init__(
        self,
        vector_db: VectorDB,
        notes_generator: SessionNotesGenerator | None = None,
    ):
        self.vector_db = vector_db
        self.notes_generator = notes_generator or HeuristicSessionNotesGenerator()

    def remember_transcript(
        self,
        transcript: str,
        session_id: str,
        guild: str = "unknown",
        channel_name: str = "unknown",
        note_path: str = "",
        session_date: str | None = None,
    ) -> SessionNotes:
        cleaned_transcript = transcript.strip()
        if not cleaned_transcript:
            raise ValueError("transcript cannot be empty")

        notes = self.notes_generator.generate_notes(cleaned_transcript, session_id)
        timestamp = datetime.now(timezone.utc).isoformat()
        metadata = self._metadata(
            session_id=session_id,
            guild=guild,
            channel_name=channel_name,
            session_date=session_date or timestamp[:10],
            note_path=note_path,
            summary_text=notes.summary,
            created_at=timestamp,
        )

        self.vector_db.add_text(
            cleaned_transcript,
            {
                **metadata,
                "kind": "transcript",
            },
        )
        self.vector_db.add_text(
            notes.summary,
            {
                **metadata,
                "kind": "session_summary",
            },
        )
        self.vector_db.add_many(
            (
                entry,
                {
                    **metadata,
                    "kind": "lore",
                },
            )
            for entry in notes.lore_entries
        )

        return notes

    def remember_note(
        self,
        note_text: str,
        session_id: str,
        summary_text: str,
        guild: str = "unknown",
        channel_name: str = "unknown",
        note_path: str = "",
        session_date: str | None = None,
    ) -> VectorRecord:
        timestamp = datetime.now(timezone.utc).isoformat()
        return self.vector_db.add_text(
            note_text,
            {
                **self._metadata(
                    session_id=session_id,
                    guild=guild,
                    channel_name=channel_name,
                    session_date=session_date or timestamp[:10],
                    note_path=note_path,
                    summary_text=summary_text,
                    created_at=timestamp,
                ),
                "kind": "note",
            },
        )

    def search_lore(self, query: str, limit: int = 5):
        return self.vector_db.search(query, limit=limit, metadata_filter={"kind": "lore"})

    def search_notes(self, query: str, limit: int = 5):
        return self.vector_db.search(query, limit=limit, metadata_filter={"kind": "note"})

    def search_session(self, query: str, session_id: str, limit: int = 5):
        return self.vector_db.search(query, limit=limit, metadata_filter={"session_id": session_id})

    def build_context(self, query: str, limit: int = 5) -> str:
        results = self.vector_db.search(query, limit=limit)
        return "\n\n".join(self._context_snippet(result) for result in results)

    def _metadata(
        self,
        *,
        session_id: str,
        guild: str,
        channel_name: str,
        session_date: str,
        note_path: str,
        summary_text: str,
        created_at: str,
    ) -> Metadata:
        return {
            "session_id": session_id,
            "guild": guild,
            "channel": channel_name,
            "session_date": session_date,
            "note_path": note_path,
            "summary_text": summary_text,
            "created_at": created_at,
        }

    def _context_snippet(self, result: SearchResult) -> str:
        metadata = result.record.metadata
        source = " | ".join(
            part
            for part in (
                metadata.get("session_date"),
                metadata.get("guild"),
                metadata.get("note_path") or metadata.get("kind"),
            )
            if part
        )
        if source:
            return f"[{source}]\n{result.record.text}"
        return result.record.text
