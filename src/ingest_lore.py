"""
Ingest arbitrary lore/reference documents (homebrew lore, rulebook notes,
campaign write-ups) into the vector store, so /recall and RAG context can
draw on them alongside auto-captured session summaries.

Run from any machine that can reach both Ollama (for embeddings) and Chroma
(config.OLLAMA_HOST / config.CHROMA_HOST) -- typically a laptop pointed at a
remote server over Tailscale or an SSH tunnel. See EXTERNAL_SERVER_SETUP.md.

Usage:
    python src/ingest_lore.py --guild-id 123456789012345678 lore/*.md

Re-running on the same file is safe (chunk IDs are deterministic per
file+index, so unchanged content just re-upserts in place). If a file
shrinks between runs, chunks past the new end are not deleted -- ingest a
fresh filename instead of heavily restructuring a file you've already
ingested.
"""

import argparse
import logging
import os

from vector_store import SessionVectorStore, chunk_text

logger = logging.getLogger(__name__)


def ingest_file(store, guild_id, path, max_chars=800, overlap=100):
    """Chunk and store one file's contents. Returns the number of chunks stored."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = chunk_text(text, max_chars=max_chars, overlap=overlap)
    source = os.path.basename(path)
    stored = 0

    for i, chunk in enumerate(chunks):
        success = store.add_document(
            doc_id=f"lore:{source}:{i}",
            text=chunk,
            metadata={
                "guild_id": str(guild_id),
                "type": "lore",
                "source": source,
                "chunk_index": i,
            },
        )
        if success:
            stored += 1
        else:
            logger.error(f"Failed to store chunk {i} of {source}")

    return stored


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ingest lore/reference documents into the vector store."
    )
    parser.add_argument("--guild-id", required=True, help="Discord guild ID these docs belong to")
    parser.add_argument("files", nargs="+", help="Text/markdown files to ingest")
    parser.add_argument("--max-chars", type=int, default=800)
    parser.add_argument("--overlap", type=int, default=100)
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    store = SessionVectorStore()
    total = 0

    for path in args.files:
        if not os.path.exists(path):
            logger.error(f"Skipping missing file: {path}")
            continue
        stored = ingest_file(store, args.guild_id, path, args.max_chars, args.overlap)
        logger.info(f"Ingested {stored} chunk(s) from {path}")
        total += stored

    logger.info(f"Done. Stored {total} chunk(s) total.")


if __name__ == "__main__":
    main()
