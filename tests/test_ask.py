import ask


class FakeStore:
    def __init__(self, results):
        self._results = results
        self.queries = []

    def query(self, guild_id, query_text, n_results=3):
        self.queries.append((guild_id, query_text, n_results))
        return self._results


class FakeResponse:
    def __init__(self, text, status_code=200):
        self._text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"status {self.status_code}")

    def json(self):
        return {"response": self._text}


def test_build_context_labels_sessions_and_lore():
    results = [
        ("The party met a dragon.", {"type": "session", "timestamp": "2026-07-01"}),
        ("The Dragon Cult worships Vashtok.", {"type": "lore", "source": "homebrew.md"}),
    ]

    context = ask.build_context(results)

    assert "[session - 2026-07-01] The party met a dragon." in context
    assert "[lore - homebrew.md] The Dragon Cult worships Vashtok." in context


def test_ask_returns_message_when_no_results_found():
    store = FakeStore(results=[])

    answer, results = ask.ask(store, guild_id=1, question="Who is the dragon cult leader?")

    assert "No relevant sessions or lore found" in answer
    assert results == []


def test_ask_queries_store_and_generates_answer(monkeypatch):
    store = FakeStore(
        results=[("The Dragon Cult leader is Vashtok.", {"type": "lore", "source": "lore.md"})]
    )

    def fake_post(url, json=None, timeout=None):
        assert "Vashtok" in json["prompt"]
        assert "Who leads the dragon cult?" in json["prompt"]
        return FakeResponse("Vashtok leads the Dragon Cult.")

    monkeypatch.setattr(ask.requests, "post", fake_post)

    answer, results = ask.ask(store, guild_id=1, question="Who leads the dragon cult?")

    assert answer == "Vashtok leads the Dragon Cult."
    assert results == store._results
    assert store.queries == [(1, "Who leads the dragon cult?", 5)]


def test_ask_degrades_gracefully_when_ollama_unreachable(monkeypatch):
    store = FakeStore(results=[("Some lore.", {"type": "lore", "source": "lore.md"})])

    def failing_post(url, json=None, timeout=None):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(ask.requests, "post", failing_post)

    answer, results = ask.ask(store, guild_id=1, question="Anything?")

    assert "couldn't reach Ollama" in answer
    assert results == store._results
