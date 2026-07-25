import ingest_lore
import vector_store


class FakeStore:
    def __init__(self):
        self.calls = []

    def add_document(self, doc_id, text, metadata):
        self.calls.append((doc_id, text, metadata))
        return True


def test_ingest_file_chunks_and_stores_with_lore_metadata(tmp_path):
    path = tmp_path / "homebrew.md"
    path.write_text("First paragraph.\n\nSecond paragraph.")

    store = FakeStore()
    stored = ingest_lore.ingest_file(store, guild_id=42, path=str(path), max_chars=800)

    assert stored == 1
    doc_id, text, metadata = store.calls[0]
    assert doc_id == "lore:homebrew.md:0"
    assert "First paragraph." in text
    assert "Second paragraph." in text
    assert metadata == {
        "guild_id": "42",
        "type": "lore",
        "source": "homebrew.md",
        "chunk_index": 0,
    }


def test_ingest_file_stores_one_entry_per_chunk(tmp_path):
    path = tmp_path / "big_lore.md"
    path.write_text(("A" * 500) + "\n\n" + ("B" * 500))

    store = FakeStore()
    stored = ingest_lore.ingest_file(store, guild_id=1, path=str(path), max_chars=800)

    assert stored == 2
    assert [call[0] for call in store.calls] == ["lore:big_lore.md:0", "lore:big_lore.md:1"]


def test_ingest_file_counts_only_successful_stores(tmp_path):
    path = tmp_path / "lore.md"
    path.write_text(("A" * 500) + "\n\n" + ("B" * 500))

    class PartiallyFailingStore:
        def __init__(self):
            self.calls = 0

        def add_document(self, doc_id, text, metadata):
            self.calls += 1
            return self.calls == 1  # only the first chunk "succeeds"

    store = PartiallyFailingStore()
    stored = ingest_lore.ingest_file(store, guild_id=1, path=str(path), max_chars=800)

    assert stored == 1
    assert store.calls == 2


def test_ingest_file_uses_real_chunk_text(tmp_path, monkeypatch):
    """Sanity-check ingest_lore actually calls vector_store.chunk_text,
    not a reimplementation, so the two never drift apart."""
    path = tmp_path / "lore.md"
    path.write_text("Some lore content.")

    captured = {}
    original_chunk_text = vector_store.chunk_text

    def spy_chunk_text(text, **kwargs):
        captured["called_with"] = text
        return original_chunk_text(text, **kwargs)

    monkeypatch.setattr(ingest_lore, "chunk_text", spy_chunk_text)

    store = FakeStore()
    ingest_lore.ingest_file(store, guild_id=1, path=str(path))

    assert captured["called_with"] == "Some lore content."
