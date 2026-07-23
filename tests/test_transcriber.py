import pytest

import transcriber


class DummySegment:
    def __init__(self, start, text):
        self.start = start
        self.text = text


class DummyModel:
    def __init__(self, *args, **kwargs):
        pass

    def transcribe(self, audio_file_path, beam_size=5):
        responses = {
            "alice.wav": [DummySegment(5.0, "Hello there")],
            "bob.wav": [DummySegment(1.0, "Hi Alice")],
        }
        for suffix, segments in responses.items():
            if audio_file_path.endswith(suffix):
                return segments, {}
        return [], {}


class DummyResponse:
    def __init__(self, status_code=200, response_text=None):
        self.status_code = status_code
        self._response_text = response_text or {"response": "Fake summary"}

    def json(self):
        return self._response_text


@pytest.fixture(autouse=True)
def patch_whisper_model(monkeypatch):
    monkeypatch.setattr(transcriber, "WhisperModel", DummyModel)
    yield


def test_transcribe_speakers_merges_by_time_and_labels_characters():
    t = transcriber.Transcriber()
    user_files = {"1": "recordings/alice.wav", "2": "recordings/bob.wav"}
    character_map = {"1": {"name": "Aria"}}

    result = t.transcribe_speakers(user_files, character_map)
    lines = result.split("\n")

    assert len(lines) == 2
    # Bob's segment starts earlier (1.0s) than Alice's (5.0s), despite being
    # listed second in user_files, so it should be merged in first.
    assert "User 2: Hi Alice" in lines[0]
    assert "Aria: Hello there" in lines[1]


def test_save_obsidian_note_writes_markdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(transcriber, "__file__", str(tmp_path / "src" / "transcriber.py"))

    t = transcriber.Transcriber()
    path = t.save_obsidian_note(
        "Session summary", {"alice": {"name": "Aria", "class": "Wizard", "species": "Elf"}}, session_name="Test" 
    )

    assert path is not None
    assert (tmp_path / "obsidian_notes").exists()
    content = (tmp_path / path).read_text(encoding="utf-8")
    assert "Session summary" in content
    assert "Aria" in content


def test_summarize_with_llm_returns_response(monkeypatch):
    t = transcriber.Transcriber()

    def fake_post(url, json=None, **kwargs):
        return DummyResponse(status_code=200)

    monkeypatch.setattr(transcriber.requests, "post", fake_post)
    response = t.summarize_with_llm("Some transcription", {"alice": {"name": "Aria"}})

    assert response == "Fake summary"


def test_summarize_with_llm_includes_prior_context_when_given(monkeypatch):
    t = transcriber.Transcriber()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured["prompt"] = json["prompt"]
        return DummyResponse(status_code=200)

    monkeypatch.setattr(transcriber.requests, "post", fake_post)
    t.summarize_with_llm(
        "Some transcription", {}, prior_context="[2026-06-01] The party met a dragon."
    )

    assert "Relevant notes from earlier sessions" in captured["prompt"]
    assert "The party met a dragon." in captured["prompt"]


def test_summarize_with_llm_omits_context_block_when_absent(monkeypatch):
    t = transcriber.Transcriber()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured["prompt"] = json["prompt"]
        return DummyResponse(status_code=200)

    monkeypatch.setattr(transcriber.requests, "post", fake_post)
    t.summarize_with_llm("Some transcription", {})

    assert "Relevant notes from earlier sessions" not in captured["prompt"]


def test_summarize_with_llm_handles_errors(monkeypatch):
    t = transcriber.Transcriber()

    def fake_post_raises(*args, **kwargs):
        raise RuntimeError("network failure")

    monkeypatch.setattr(transcriber.requests, "post", fake_post_raises)
    response = t.summarize_with_llm("Some transcription", {})

    assert "Summary unavailable" in response
