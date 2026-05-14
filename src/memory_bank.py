from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Protocol

from vector_db import Metadata, SearchResult, VectorDB, VectorRecord

PUBLIC = "public"
CHARACTER = "character"
DM_ONLY = "dm"
MEMORY_SCOPES = {PUBLIC, CHARACTER, DM_ONLY}
NO_MEMORY_FOUND = "No matching campaign memory found."
NO_SESSION_RECAP_FOUND = "No session recap found yet."


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
        visibility: str = PUBLIC,
        owner_user_id: str = "",
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
            visibility=visibility,
            owner_user_id=owner_user_id,
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
        visibility: str = PUBLIC,
        owner_user_id: str = "",
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
                    visibility=visibility,
                    owner_user_id=owner_user_id,
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

    def search_accessible(
        self,
        query: str,
        user_id: str,
        dm_access: bool = False,
        guild: str = "",
        limit: int = 5,
    ) -> list[SearchResult]:
        metadata_filter = {"guild": guild} if guild else None
        results = self.vector_db.search(
            query,
            limit=max(limit * 4, limit),
            metadata_filter=metadata_filter,
        )
        accessible = [
            result
            for result in results
            if self._can_read(result.record.metadata, user_id, dm_access)
        ]
        return accessible[:limit]

    def last_session_recap(
        self,
        guild: str,
        user_id: str,
        dm_access: bool = False,
    ) -> str:
        records = [
            record
            for record in self.vector_db.records
            if record.metadata.get("guild") == guild
            and self._can_read(record.metadata, user_id, dm_access)
        ]
        summaries = [
            record for record in records if record.metadata.get("kind") == "session_summary"
        ]
        if not summaries:
            return NO_SESSION_RECAP_FOUND

        summary = max(summaries, key=_session_sort_key)
        session_id = summary.metadata.get("session_id", "")
        lore = [
            record
            for record in records
            if record.metadata.get("session_id") == session_id
            and record.metadata.get("kind") == "lore"
        ]
        return format_session_recap(summary, lore)

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
        visibility: str,
        owner_user_id: str,
    ) -> Metadata:
        return {
            "session_id": session_id,
            "guild": guild,
            "channel": channel_name,
            "session_date": session_date,
            "note_path": note_path,
            "summary_text": summary_text,
            "created_at": created_at,
            "visibility": visibility,
            "owner_user_id": owner_user_id,
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

    def _can_read(self, metadata: Metadata, user_id: str, dm_access: bool) -> bool:
        visibility = metadata.get("visibility") or PUBLIC
        if visibility == DM_ONLY:
            return dm_access
        if visibility == CHARACTER:
            return dm_access or metadata.get("owner_user_id") == user_id
        return True


def normalize_visibility(scope: str | None) -> str | None:
    normalized = (scope or PUBLIC).strip().lower()
    if normalized in MEMORY_SCOPES:
        return normalized
    return None


def format_memory_results(results: list[SearchResult], max_length: int = 1900) -> str:
    if not results:
        return NO_MEMORY_FOUND

    lines = []
    for result in results:
        metadata = result.record.metadata
        source = " | ".join(
            value
            for value in (
                metadata.get("session_date"),
                metadata.get("kind"),
                metadata.get("note_path"),
            )
            if value
        )
        text = " ".join(result.record.text.split())
        if len(text) > 600:
            text = f"{text[:597]}..."
        lines.append(f"**{source or 'memory'}**\n{text}")

    message = "\n\n".join(lines)
    if len(message) > max_length:
        return f"{message[:max_length - 3]}..."
    return message


def format_session_recap(
    summary: VectorRecord,
    lore: list[VectorRecord],
    max_length: int = 1900,
) -> str:
    metadata = summary.metadata
    session_label = metadata.get("session_date") or metadata.get("session_id") or "last session"
    lines = [
        f"**Last Session: {session_label}**",
        " ".join(summary.text.split()),
    ]
    if lore:
        lines.append("")
        lines.append("**Lore**")
        lines.extend(f"- {' '.join(record.text.split())}" for record in lore[:5])

    message = "\n".join(lines)
    if len(message) > max_length:
        return f"{message[:max_length - 3]}..."
    return message


def _session_sort_key(record: VectorRecord) -> tuple[str, str, str]:
    metadata = record.metadata
    return (
        metadata.get("session_date", ""),
        metadata.get("session_id", ""),
        metadata.get("created_at", ""),
    )
