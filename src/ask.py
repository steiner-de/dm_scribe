"""
Ask a question against the vector store (past session summaries + ingested
lore) and get back a synthesized answer, not just raw matching chunks.

Run from any machine that can reach both Ollama and Chroma
(config.OLLAMA_HOST / config.CHROMA_HOST) -- see EXTERNAL_SERVER_SETUP.md.

Usage:
    python src/ask.py --guild-id 123456789012345678 "Who leads the dragon cult?"
"""

import argparse
import logging

import requests

from config import OLLAMA_HOST, OLLAMA_MODEL
from vector_store import SessionVectorStore

logger = logging.getLogger(__name__)

ANSWER_PROMPT_TEMPLATE = """You are a D&D campaign assistant. Answer the question using
only the context below, drawn from past session summaries and campaign lore. If the
context doesn't contain the answer, say so plainly rather than guessing.

Context:
{context}

Question: {question}

Answer:
"""


def build_context(results):
    """Render (document, metadata) query results into a labeled context block."""
    return "\n\n".join(
        f"[{meta.get('type', 'unknown')} - {meta.get('source') or meta.get('timestamp', '')}] "
        f"{doc}"
        for doc, meta in results
    )


def ask(store, guild_id, question, n_results=5):
    """
    Retrieve relevant chunks for `question` and ask Ollama to synthesize an
    answer from them.

    Returns (answer, results) -- results is the raw list of (doc, metadata)
    tuples used as context, so callers can also show sources.
    """
    results = store.query(guild_id, question, n_results=n_results)
    if not results:
        return (
            "No relevant sessions or lore found (or the vector store/Ollama isn't reachable).",
            [],
        )

    prompt = ANSWER_PROMPT_TEMPLATE.format(context=build_context(results), question=question)

    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        response.raise_for_status()
        answer = response.json()["response"]
    except Exception as e:
        logger.error(f"Failed to generate answer: {e}")
        answer = "Found relevant context, but couldn't reach Ollama to generate an answer."

    return answer, results


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ask a question against past sessions + ingested lore."
    )
    parser.add_argument("--guild-id", required=True, help="Discord guild ID to search within")
    parser.add_argument("--n-results", type=int, default=5)
    parser.add_argument("question", help="The question to ask")
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.WARNING)
    args = parse_args()

    store = SessionVectorStore()
    answer, results = ask(store, args.guild_id, args.question, n_results=args.n_results)

    print(f"\n{answer}\n")
    if results:
        print("Sources:")
        for doc, meta in results:
            label = meta.get("source") or f"session {meta.get('timestamp', 'unknown date')}"
            print(f"  - {label}: {doc[:100]}...")


if __name__ == "__main__":
    main()
