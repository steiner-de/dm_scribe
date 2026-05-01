from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from pathlib import Path
import re
from typing import Any, Iterable, Protocol, Sequence
from uuid import uuid4

import lancedb


Metadata = dict[str, Any]
_METADATA_FIELDS = ("kind", "session_id", "channel", "created_at")


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> Sequence[float]:
        ...


@dataclass(frozen=True)
class VectorRecord:
    id: str
    text: str
    embedding: list[float]
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    record: VectorRecord
    score: float


class HashingEmbeddingProvider:
    _token_pattern = re.compile(r"[a-z0-9']+")

    def __init__(self, dimensions: int = 256):
        if dimensions <= 0:
            raise ValueError("dimensions must be greater than zero")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _normalize(vector)

    def _tokens(self, text: str) -> Iterable[str]:
        return self._token_pattern.findall(text.lower())


class VectorDB:
    def __init__(
        self,
        path: str | Path,
        embedder: EmbeddingProvider | None = None,
        table_name: str = "campaign_memory",
    ):
        self.path = Path(path)
        self.embedder = embedder or HashingEmbeddingProvider()
        self.table_name = table_name
        self._db = lancedb.connect(str(self.path))

    @property
    def records(self) -> tuple[VectorRecord, ...]:
        if not self._table_exists():
            return ()
        return tuple(_row_to_record(row) for row in self._table().to_arrow().to_pylist())

    def add_text(
        self,
        text: str,
        metadata: Metadata | None = None,
        record_id: str | None = None,
    ) -> VectorRecord:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("text cannot be empty")

        record = VectorRecord(
            id=record_id or uuid4().hex,
            text=cleaned_text,
            metadata=_known_metadata(metadata),
            embedding=list(self.embedder.embed(cleaned_text)),
        )
        row = _record_to_row(record)

        if self._table_exists():
            self._table().add([row])
        else:
            self._db.create_table(self.table_name, data=[row])

        return record

    def add_many(self, entries: Iterable[tuple[str, Metadata | None]]) -> list[VectorRecord]:
        records = []
        for text, metadata in entries:
            cleaned_text = text.strip()
            if cleaned_text:
                records.append(
                    VectorRecord(
                        id=uuid4().hex,
                        text=cleaned_text,
                        metadata=_known_metadata(metadata),
                        embedding=list(self.embedder.embed(cleaned_text)),
                    )
                )

        if not records:
            return []

        rows = [_record_to_row(record) for record in records]
        if self._table_exists():
            self._table().add(rows)
        else:
            self._db.create_table(self.table_name, data=rows)

        return records

    def search(
        self,
        query: str,
        limit: int = 5,
        metadata_filter: Metadata | None = None,
    ) -> list[SearchResult]:
        cleaned_query = query.strip()
        if limit <= 0 or not cleaned_query or not self._table_exists():
            return []

        query_embedding = list(self.embedder.embed(cleaned_query))
        search = self._table().search(query_embedding)
        where_clause = _where_clause(metadata_filter)
        if where_clause:
            search = search.where(where_clause)

        rows = search.limit(limit).to_list()
        return [_row_to_result(row) for row in rows]

    def _table(self):
        return self._db.open_table(self.table_name)

    def _table_exists(self) -> bool:
        return self.table_name in self._db.list_tables().tables


def _known_metadata(metadata: Metadata | None) -> Metadata:
    source = metadata or {}
    return {field: str(source.get(field, "")) for field in _METADATA_FIELDS}


def _record_to_row(record: VectorRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "text": record.text,
        "vector": record.embedding,
        **_known_metadata(record.metadata),
    }


def _row_to_record(row: dict[str, Any]) -> VectorRecord:
    return VectorRecord(
        id=row["id"],
        text=row["text"],
        embedding=[float(value) for value in row["vector"]],
        metadata={field: row.get(field, "") for field in _METADATA_FIELDS},
    )


def _row_to_result(row: dict[str, Any]) -> SearchResult:
    distance = float(row.get("_distance", 0.0))
    return SearchResult(record=_row_to_record(row), score=1.0 / (1.0 + distance))


def _where_clause(metadata_filter: Metadata | None) -> str:
    if not metadata_filter:
        return ""

    clauses = []
    for field, value in metadata_filter.items():
        if field not in _METADATA_FIELDS:
            raise ValueError(f"Unsupported metadata filter: {field}")
        clauses.append(f"{field} = '{_escape_sql_value(str(value))}'")
    return " AND ".join(clauses)


def _escape_sql_value(value: str) -> str:
    return value.replace("'", "''")


def _normalize(vector: Sequence[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return [0.0 for _ in vector]
    return [value / magnitude for value in vector]
