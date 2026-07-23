import pytest

import vector_store


class FakeResponse:
    def __init__(self, embedding):
        self._embedding = embedding

    def raise_for_status(self):
        pass

    def json(self):
        return {"embedding": self._embedding}


def _fake_embedding_for(text):
    """Deterministic, fixed-dimension stand-in for a real embedding call."""
    return [float(len(text) % 7), float(hash(text) % 11), float(len(text.split()) % 5)]


@pytest.fixture
def patch_embeddings(monkeypatch):
    monkeypatch.setattr(vector_store, "embed_text", lambda text: _fake_embedding_for(text))


def test_embed_text_posts_to_ollama_and_returns_embedding(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse([0.1, 0.2, 0.3])

    monkeypatch.setattr(vector_store.requests, "post", fake_post)

    result = vector_store.embed_text("hello world")

    assert result == [0.1, 0.2, 0.3]
    assert captured["url"] == vector_store.OLLAMA_EMBED_URL
    assert captured["json"]["prompt"] == "hello world"


def test_add_session_then_query_returns_it(tmp_path, patch_embeddings):
    store = vector_store.SessionVectorStore(persist_dir=str(tmp_path))

    added = store.add_session(
        guild_id=1,
        session_id="abc123",
        timestamp="2026-07-01",
        channel_name="general",
        characters=["Thrain", "Elric"],
        summary="The party fought a dragon and found treasure.",
    )
    assert added is True

    results = store.query(guild_id=1, query_text="dragon fight", n_results=3)

    assert len(results) == 1
    doc, meta = results[0]
    assert doc == "The party fought a dragon and found treasure."
    assert meta["guild_id"] == "1"
    assert meta["timestamp"] == "2026-07-01"
    assert meta["characters"] == "Thrain, Elric"


def test_query_filters_by_guild_id(tmp_path, patch_embeddings):
    store = vector_store.SessionVectorStore(persist_dir=str(tmp_path))

    store.add_session(1, "s1", "2026-07-01", "general", ["Thrain"], "Guild one session.")
    store.add_session(2, "s2", "2026-07-01", "general", ["Zog"], "Guild two session.")

    results = store.query(guild_id=1, query_text="session", n_results=5)

    assert len(results) == 1
    assert results[0][0] == "Guild one session."


def test_add_session_skips_empty_summary(tmp_path, patch_embeddings):
    store = vector_store.SessionVectorStore(persist_dir=str(tmp_path))

    assert store.add_session(1, "s1", "2026-07-01", "general", [], "") is False
    assert store.add_session(1, "s2", "2026-07-01", "general", [], "   ") is False


def test_add_session_returns_false_when_embedding_fails(tmp_path, monkeypatch):
    store = vector_store.SessionVectorStore(persist_dir=str(tmp_path))

    def failing_embed(text):
        raise RuntimeError("Ollama unreachable")

    monkeypatch.setattr(vector_store, "embed_text", failing_embed)

    assert store.add_session(1, "s1", "2026-07-01", "general", [], "A summary.") is False


def test_query_returns_empty_list_when_embedding_fails(tmp_path, monkeypatch):
    store = vector_store.SessionVectorStore(persist_dir=str(tmp_path))

    def failing_embed(text):
        raise RuntimeError("Ollama unreachable")

    monkeypatch.setattr(vector_store, "embed_text", failing_embed)

    assert store.query(1, "anything") == []
