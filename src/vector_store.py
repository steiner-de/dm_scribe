"""
Vector store for D&D session summaries and lore/reference material.

Backed by Chroma, either embedded (file-based, persists under
config.VECTOR_STORE_DIR, no server needed) or networked (a `chroma run`
server, when config.CHROMA_HOST is set) -- networked mode is what lets
src/ingest_lore.py and src/ask.py reach the same store from a different
machine than the one running the bot. Embeddings come from Ollama
(config.OLLAMA_HOST), which likewise must be reachable from wherever the
calling process runs.

Used three ways:
  - RAG: retrieve related past sessions to feed into the summarization
    prompt for continuity across sessions (see bot.process_recording).
  - Search: the /recall command lets a DM semantically search past
    sessions from Discord.
  - Lore ingestion: src/ingest_lore.py loads arbitrary reference documents
    (homebrew lore, rulebook notes) in so /recall and RAG can draw on them
    too, not just auto-captured session summaries.

Every entry (session or lore) carries a "guild_id" field in its metadata,
and queries always filter on it -- so one server's data never leaks into
another's.
"""

import logging

import chromadb
import requests
from chromadb.config import Settings

from config import CHROMA_HOST, CHROMA_PORT, OLLAMA_EMBEDDING_MODEL, OLLAMA_HOST, VECTOR_STORE_DIR

logger = logging.getLogger(__name__)

COLLECTION_NAME = "dnd_sessions"
OLLAMA_EMBED_URL = f"{OLLAMA_HOST}/api/embeddings"
EMBED_TIMEOUT = 30


def embed_text(text: str):
    """Get an embedding vector for text from Ollama's embedding model."""
    response = requests.post(
        OLLAMA_EMBED_URL,
        json={"model": OLLAMA_EMBEDDING_MODEL, "prompt": text},
        timeout=EMBED_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["embedding"]


def chunk_text(text, max_chars=800, overlap=100):
    """
    Split text into chunks for embedding -- a single embedding call can't
    meaningfully represent an entire long document. Whole paragraphs are
    packed together up to max_chars; a paragraph longer than max_chars on
    its own is hard-split with overlap so no content is silently dropped.

    Used by src/ingest_lore.py to prepare long lore/reference documents.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(paragraph):
                end = start + max_chars
                chunks.append(paragraph[start:end])
                if end >= len(paragraph):
                    break
                start = end - overlap
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


class SessionVectorStore:
    def __init__(self, persist_dir=None):
        if CHROMA_HOST:
            self.client = chromadb.HttpClient(
                host=CHROMA_HOST,
                port=CHROMA_PORT,
                settings=Settings(anonymized_telemetry=False),
            )
        else:
            self.client = chromadb.PersistentClient(
                path=persist_dir or VECTOR_STORE_DIR,
                settings=Settings(anonymized_telemetry=False),
            )
        self.collection = self.client.get_or_create_collection(COLLECTION_NAME)

    def add_document(self, doc_id, text, metadata):
        """
        Embed and store an arbitrary document -- a session summary or a
        lore/reference chunk (see src/ingest_lore.py) -- under doc_id.
        metadata must include "guild_id" (queries always filter on it).

        Returns True on success, False if embedding/storage failed (e.g.
        Ollama unreachable) -- callers should treat this as non-fatal.
        """
        if not text or not text.strip():
            return False

        try:
            embedding = embed_text(text)
        except Exception as e:
            logger.error(f"Failed to embed document {doc_id} for vector store: {e}")
            return False

        try:
            self.collection.upsert(
                ids=[str(doc_id)],
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata],
            )
        except Exception as e:
            logger.error(f"Failed to store document {doc_id} in vector store: {e}")
            return False

        return True

    def add_session(self, guild_id, session_id, timestamp, channel_name, characters, summary):
        """Embed and store a session summary for later retrieval."""
        return self.add_document(
            doc_id=session_id,
            text=summary,
            metadata={
                "guild_id": str(guild_id),
                "timestamp": timestamp,
                "channel": channel_name or "unknown",
                "characters": ", ".join(characters) if characters else "",
                "type": "session",
            },
        )

    def query(self, guild_id, query_text, n_results=3):
        """
        Semantic search over past session summaries and ingested lore for
        one guild.

        Returns a list of (document_text, metadata) tuples, most relevant
        first. Returns [] on any failure (e.g. Ollama unreachable, or
        nothing stored yet) rather than raising, since both RAG context
        and /recall should degrade gracefully.
        """
        try:
            embedding = embed_text(query_text)
        except Exception as e:
            logger.error(f"Failed to embed vector store query: {e}")
            return []

        try:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=n_results,
                where={"guild_id": str(guild_id)},
            )
        except Exception as e:
            logger.error(f"Vector store query failed: {e}")
            return []

        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        return list(zip(documents, metadatas))
