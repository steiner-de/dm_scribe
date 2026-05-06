from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from pathlib import Path
import re
from typing import Any, Iterable, Protocol, Sequence
from uuid import uuid4

import chromadb


Metadata = dict[str, Any]
_METADATA_FIELDS = (
    "kind",
    "session_id",
    "guild",
    "channel",
    "session_date",
    "note_path",
    "summary_text",
    "created_at",
)


class EmbeddingProvider(Protocol):
    def embed(self, text: str, *, input_type: str = "document") -> Sequence[float]:
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

    def embed(self, text: str, *, input_type: str = "document") -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _normalize(vector)

    def _tokens(self, text: str) -> Iterable[str]:
        return self._token_pattern.findall(text.lower())


class NomicEmbeddingProvider:
    def __init__(
        self,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        tokenizer_name: str = "bert-base-uncased",
        device: str | None = None,
        max_length: int = 8192,
        dimensions: int = 768,
        rotary_scaling_factor: float | None = 2.0,
    ):
        if max_length <= 0:
            raise ValueError("max_length must be greater than zero")
        if dimensions <= 0 or dimensions > 768:
            raise ValueError("dimensions must be between 1 and 768")

        self.model_name = model_name
        self.tokenizer_name = tokenizer_name
        self.device = device
        self.max_length = max_length
        self.dimensions = dimensions
        self.rotary_scaling_factor = rotary_scaling_factor
        self._tokenizer = None
        self._model = None

    def embed(self, text: str, *, input_type: str = "document") -> list[float]:
        cleaned_text = text.strip()
        if not cleaned_text:
            return []

        tokenizer, model = self._load_model()

        import torch
        import torch.nn.functional as functional

        encoded = tokenizer(
            self._prefixed_text(cleaned_text, input_type),
            return_tensors="pt",
            truncation=True,
            max_length=self.max_length,
        )
        if self.device:
            encoded = {key: value.to(self.device) for key, value in encoded.items()}

        with torch.no_grad():
            output = model(**encoded)
            embedding = _mean_pool(output, encoded["attention_mask"])
            embedding = functional.layer_norm(
                embedding,
                normalized_shape=(embedding.shape[1],),
            )
            embedding = embedding[:, : self.dimensions]
            embedding = functional.normalize(embedding, p=2, dim=1)

        return [float(value) for value in embedding[0].detach().cpu().tolist()]

    def _load_model(self):
        if self._tokenizer is None or self._model is None:
            from transformers import AutoModel, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.tokenizer_name,
                model_max_length=self.max_length,
            )
            model_kwargs = {"trust_remote_code": True}
            if self.max_length > 2048 and self.rotary_scaling_factor is not None:
                model_kwargs["rotary_scaling_factor"] = self.rotary_scaling_factor
            self._model = AutoModel.from_pretrained(
                self.model_name,
                **model_kwargs,
            )
            if self.device:
                self._model = self._model.to(self.device)
            self._model.eval()
        return self._tokenizer, self._model

    def _prefixed_text(self, text: str, input_type: str) -> str:
        if input_type == "query":
            return f"search_query: {text}"
        return f"search_document: {text}"


class VectorDB:
    def __init__(
        self,
        path: str | Path,
        embedder: EmbeddingProvider | None = None,
        table_name: str = "campaign_memory",
    ):
        self.path = Path(path)
        self.embedder = embedder or NomicEmbeddingProvider()
        self.table_name = table_name
        self._client = chromadb.PersistentClient(path=str(self.path))
        self._collection = self._client.get_or_create_collection(
            name=self.table_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def records(self) -> tuple[VectorRecord, ...]:
        if self._collection.count() == 0:
            return ()
        rows = self._collection.get(include=["documents", "embeddings", "metadatas"])
        return tuple(_record_from_chroma(rows, index) for index in range(len(rows["ids"])))

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
            embedding=list(self.embedder.embed(cleaned_text, input_type="document")),
        )
        self._collection.add(
            ids=[record.id],
            documents=[record.text],
            embeddings=[record.embedding],
            metadatas=[record.metadata],
        )

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
                        embedding=list(self.embedder.embed(cleaned_text, input_type="document")),
                    )
                )

        if not records:
            return []

        self._collection.add(
            ids=[record.id for record in records],
            documents=[record.text for record in records],
            embeddings=[record.embedding for record in records],
            metadatas=[record.metadata for record in records],
        )

        return records

    def search(
        self,
        query: str,
        limit: int = 5,
        metadata_filter: Metadata | None = None,
    ) -> list[SearchResult]:
        cleaned_query = query.strip()
        if limit <= 0 or not cleaned_query or self._collection.count() == 0:
            return []

        query_embedding = list(self.embedder.embed(cleaned_query, input_type="query"))
        rows = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=_where_filter(metadata_filter),
            include=["documents", "embeddings", "metadatas", "distances"],
        )
        return [_result_from_chroma(rows, index) for index in range(len(rows["ids"][0]))]


def _known_metadata(metadata: Metadata | None) -> Metadata:
    source = metadata or {}
    return {field: str(source.get(field, "")) for field in _METADATA_FIELDS}


def _record_from_chroma(rows: dict[str, Any], index: int) -> VectorRecord:
    return VectorRecord(
        id=rows["ids"][index],
        text=rows["documents"][index],
        embedding=[float(value) for value in rows["embeddings"][index]],
        metadata={field: rows["metadatas"][index].get(field, "") for field in _METADATA_FIELDS},
    )


def _result_from_chroma(rows: dict[str, Any], index: int) -> SearchResult:
    result = {
        "ids": rows["ids"][0],
        "documents": rows["documents"][0],
        "embeddings": rows["embeddings"][0],
        "metadatas": rows["metadatas"][0],
    }
    distance = float(rows["distances"][0][index])
    return SearchResult(record=_record_from_chroma(result, index), score=1.0 / (1.0 + distance))


def _where_filter(metadata_filter: Metadata | None) -> Metadata | None:
    if not metadata_filter:
        return None

    filters = []
    for field, value in metadata_filter.items():
        if field not in _METADATA_FIELDS:
            raise ValueError(f"Unsupported metadata filter: {field}")
        filters.append({field: str(value)})
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}


def _normalize(vector: Sequence[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return [0.0 for _ in vector]
    return [value / magnitude for value in vector]


def _mean_pool(model_output: Any, attention_mask: Any) -> Any:
    token_embeddings = model_output[0]
    input_mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return (token_embeddings * input_mask).sum(1) / input_mask.sum(1).clamp(min=1e-9)
