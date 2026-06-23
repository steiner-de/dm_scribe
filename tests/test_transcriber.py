import pytest

import transcriber


class DummyModel:
    def __init__(self, *args, **kwargs):
        pass

    def transcribe(self, audio_file_path, beam_size=5):
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


def test_enhance_transcription_replaces_handles():
    t = transcriber.Transcriber()
    transcription = "Alice says hello to Bob."
    character_map = {"Alice": {"name": "Aria"}}

    result = t.enhance_transcription(transcription, character_map)

    assert "Aria says hello to Bob." in result


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


def test_summarize_with_llm_handles_errors(monkeypatch):
    t = transcriber.Transcriber()

    def fake_post_raises(*args, **kwargs):
        raise RuntimeError("network failure")

    monkeypatch.setattr(transcriber.requests, "post", fake_post_raises)
    response = t.summarize_with_llm("Some transcription", {})

    assert "Summary unavailable" in response
