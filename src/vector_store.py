"""
Local vector store for past D&D session summaries.

Backed by Chroma (file-based, no server needed -- persists under
config.VECTOR_STORE_DIR) with embeddings from Ollama's embedding model.
Used two ways:
  - RAG: retrieve related past sessions to feed into the summarization
    prompt for continuity across sessions (see bot.process_recording).
  - Search: the /recall command lets a DM semantically search past
    sessions from Discord.

Every guild's sessions live in the same Chroma collection, distinguished
by a "guild_id" field in each entry's metadata, and queries always filter
on it -- so one server's session history never leaks into another's.
"""

import logging

import chromadb
import requests
from chromadb.config import Settings

from config import OLLAMA_EMBEDDING_MODEL, VECTOR_STORE_DIR

logger = logging.getLogger(__name__)

COLLECTION_NAME = "dnd_sessions"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
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


class SessionVectorStore:
    def __init__(self, persist_dir=None):
        self.client = chromadb.PersistentClient(
            path=persist_dir or VECTOR_STORE_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(COLLECTION_NAME)

    def add_session(self, guild_id, session_id, timestamp, channel_name, characters, summary):
        """Embed and store a session summary for later retrieval.

        Returns True on success, False if embedding/storage failed (e.g.
        Ollama unreachable) -- callers should treat this as non-fatal.
        """
        if not summary or not summary.strip():
            return False

        try:
            embedding = embed_text(summary)
        except Exception as e:
            logger.error(f"Failed to embed session {session_id} for vector store: {e}")
            return False

        try:
            self.collection.upsert(
                ids=[str(session_id)],
                embeddings=[embedding],
                documents=[summary],
                metadatas=[
                    {
                        "guild_id": str(guild_id),
                        "timestamp": timestamp,
                        "channel": channel_name or "unknown",
                        "characters": ", ".join(characters) if characters else "",
                    }
                ],
            )
        except Exception as e:
            logger.error(f"Failed to store session {session_id} in vector store: {e}")
            return False

        return True

    def query(self, guild_id, query_text, n_results=3):
        """
        Semantic search over past session summaries for one guild.

        Returns a list of (summary_text, metadata) tuples, most relevant
        first. Returns [] on any failure (e.g. Ollama unreachable, or no
        sessions stored yet) rather than raising, since both RAG context
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
