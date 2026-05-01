from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Protocol

from vector_db import VectorDB


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
        channel_name: str = "unknown",
    ) -> SessionNotes:
        cleaned_transcript = transcript.strip()
        if not cleaned_transcript:
            raise ValueError("transcript cannot be empty")

        notes = self.notes_generator.generate_notes(cleaned_transcript, session_id)
        timestamp = datetime.now(timezone.utc).isoformat()

        self.vector_db.add_text(
            cleaned_transcript,
            {
                "kind": "transcript",
                "session_id": session_id,
                "channel": channel_name,
                "created_at": timestamp,
            },
        )
        self.vector_db.add_text(
            notes.summary,
            {
                "kind": "session_summary",
                "session_id": session_id,
                "channel": channel_name,
                "created_at": timestamp,
            },
        )
        self.vector_db.add_many(
            (
                entry,
                {
                    "kind": "lore",
                    "session_id": session_id,
                    "channel": channel_name,
                    "created_at": timestamp,
                },
            )
            for entry in notes.lore_entries
        )

        return notes

    def search_lore(self, query: str, limit: int = 5):
        return self.vector_db.search(query, limit=limit, metadata_filter={"kind": "lore"})

    def search_session(self, query: str, session_id: str, limit: int = 5):
        return self.vector_db.search(query, limit=limit, metadata_filter={"session_id": session_id})
