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


def test_add_document_stores_arbitrary_metadata(tmp_path, patch_embeddings):
    store = vector_store.SessionVectorStore(persist_dir=str(tmp_path))

    added = store.add_document(
        doc_id="lore:homebrew.md:0",
        text="The Dragon Cult worships an ancient wyrm named Vashtok.",
        metadata={"guild_id": "1", "type": "lore", "source": "homebrew.md", "chunk_index": 0},
    )
    assert added is True

    results = store.query(guild_id=1, query_text="dragon cult", n_results=3)
    assert len(results) == 1
    doc, meta = results[0]
    assert "Vashtok" in doc
    assert meta["type"] == "lore"
    assert meta["source"] == "homebrew.md"


def test_chunk_text_empty_string_returns_no_chunks():
    assert vector_store.chunk_text("") == []
    assert vector_store.chunk_text("   \n\n  ") == []


def test_chunk_text_short_text_is_a_single_chunk():
    text = "A short paragraph about the dragon cult."
    assert vector_store.chunk_text(text, max_chars=800) == [text]


def test_chunk_text_packs_multiple_paragraphs_up_to_max_chars():
    para_a = "A" * 300
    para_b = "B" * 300
    text = f"{para_a}\n\n{para_b}"

    chunks = vector_store.chunk_text(text, max_chars=800)

    assert len(chunks) == 1
    assert para_a in chunks[0]
    assert para_b in chunks[0]


def test_chunk_text_starts_new_chunk_when_max_chars_exceeded():
    para_a = "A" * 500
    para_b = "B" * 500
    text = f"{para_a}\n\n{para_b}"

    chunks = vector_store.chunk_text(text, max_chars=800)

    assert chunks == [para_a, para_b]


def test_chunk_text_hard_splits_overlong_paragraph_with_overlap():
    # A distinguishable (non-uniform) sequence so overlap positions are
    # actually verified, rather than trivially matching on repeated chars.
    paragraph = "".join(str(i % 10) for i in range(1000))

    chunks = vector_store.chunk_text(paragraph, max_chars=400, overlap=50)

    assert len(chunks) > 1
    assert all(len(c) <= 400 for c in chunks)
    assert chunks[0][-50:] == chunks[1][:50]


def test_uses_http_client_when_chroma_host_configured(monkeypatch, tmp_path):
    captured = {}

    class FakeCollection:
        pass

    class FakeHttpClient:
        def __init__(self, host, port, settings):
            captured["mode"] = "http"
            captured["host"] = host
            captured["port"] = port

        def get_or_create_collection(self, name):
            return FakeCollection()

    class FakePersistentClient:
        def __init__(self, path, settings):
            captured["mode"] = "persistent"

        def get_or_create_collection(self, name):
            return FakeCollection()

    monkeypatch.setattr(vector_store, "CHROMA_HOST", "desktop.local")
    monkeypatch.setattr(vector_store, "CHROMA_PORT", 8000)
    monkeypatch.setattr(vector_store.chromadb, "HttpClient", FakeHttpClient)
    monkeypatch.setattr(vector_store.chromadb, "PersistentClient", FakePersistentClient)

    vector_store.SessionVectorStore(persist_dir=str(tmp_path))

    assert captured == {"mode": "http", "host": "desktop.local", "port": 8000}


def test_uses_persistent_client_when_chroma_host_not_set(monkeypatch, tmp_path):
    captured = {}

    class FakeCollection:
        pass

    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            captured["mode"] = "http"

        def get_or_create_collection(self, name):
            return FakeCollection()

    class FakePersistentClient:
        def __init__(self, path, settings):
            captured["mode"] = "persistent"
            captured["path"] = path

        def get_or_create_collection(self, name):
            return FakeCollection()

    monkeypatch.setattr(vector_store, "CHROMA_HOST", None)
    monkeypatch.setattr(vector_store.chromadb, "HttpClient", FakeHttpClient)
    monkeypatch.setattr(vector_store.chromadb, "PersistentClient", FakePersistentClient)

    vector_store.SessionVectorStore(persist_dir=str(tmp_path))

    assert captured == {"mode": "persistent", "path": str(tmp_path)}
