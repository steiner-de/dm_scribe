import json
import wave

import pytest

import utils


class DummyUser:
    def __init__(self, display_name=None):
        if display_name is not None:
            self.display_name = display_name


def test_sanitize_text_removes_extra_whitespace():
    text = "  This   is   a   test  "
    assert utils.sanitize_text(text) == "This is a test"


def test_format_timestamp_returns_string():
    timestamp = utils.format_timestamp()
    assert isinstance(timestamp, str)
    assert len(timestamp) > 0


def test_get_user_display_name_with_display_name():
    user = DummyUser(display_name="Test User")
    assert utils.get_user_display_name(user) == "Test User"


def test_get_user_display_name_without_display_name():
    user = DummyUser()
    assert utils.get_user_display_name(user) == str(user)


def test_save_transcript_for_training_creates_file(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(utils, "__file__", str(repo_root / "src" / "utils.py"))

    utils.save_transcript_for_training("Hello world", "A hero says hi.", "session1", "general")

    training_data = repo_root / "training_data"
    files = list(training_data.glob("transcript_session1_*.json"))
    assert files
    data = json.loads(files[0].read_text())
    assert data["session_id"] == "session1"
    assert data["channel"] == "general"
    assert data["transcript"] == "Hello world"
    assert data["summary"] == "A hero says hi."


def test_export_training_data_builds_instruction_response_pairs(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    training_data = repo_root / "training_data"
    training_data.mkdir(parents=True)
    output_path = repo_root / "exported_training_data.jsonl"

    sample = {
        "session_id": "session1",
        "channel": "general",
        "timestamp": "2026-06-18 00:00:00",
        "transcript": "Hello world",
        "summary": "A hero says hi.",
        "source": "discord_voice_call",
    }
    sample_file = training_data / "transcript_session1_test.json"
    sample_file.write_text(json.dumps(sample))

    monkeypatch.setattr(utils, "__file__", str(repo_root / "src" / "utils.py"))
    result = utils.export_training_data(output_path=str(output_path))

    assert result == str(output_path)
    assert output_path.exists()
    lines = output_path.read_text().strip().splitlines()
    assert len(lines) == 1

    example = json.loads(lines[0])
    assert "Hello world" in example["instruction"]
    assert example["response"] == "A hero says hi."


def test_export_training_data_skips_records_without_summary(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    training_data = repo_root / "training_data"
    training_data.mkdir(parents=True)
    output_path = repo_root / "exported_training_data.jsonl"

    legacy_sample = {
        "session_id": "old",
        "channel": "general",
        "timestamp": "2026-06-18 00:00:00",
        "transcript": "Hello world",
        "source": "discord_voice_call",
    }
    (training_data / "transcript_old_test.json").write_text(json.dumps(legacy_sample))

    monkeypatch.setattr(utils, "__file__", str(repo_root / "src" / "utils.py"))
    result = utils.export_training_data(output_path=str(output_path))

    assert result == str(output_path)
    assert output_path.read_text().strip() == ""


def test_get_wav_duration_seconds_reads_real_wav_file(tmp_path):
    path = tmp_path / "test.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x00" * 3200)  # 1600 frames at 16kHz = 0.1s

    assert utils.get_wav_duration_seconds(str(path)) == pytest.approx(0.1)


def test_get_wav_duration_seconds_returns_zero_for_missing_file(tmp_path):
    missing_path = str(tmp_path / "does_not_exist.wav")

    assert utils.get_wav_duration_seconds(missing_path) == 0.0


def test_log_session_metrics_appends_json_line(tmp_path, monkeypatch):
    metrics_file = tmp_path / "session_metrics.jsonl"
    monkeypatch.setattr(utils, "SESSION_METRICS_FILE", str(metrics_file))

    utils.log_session_metrics(speaker_count=3, transcription_seconds=12.5)
    utils.log_session_metrics(speaker_count=1, transcription_seconds=4.2)

    lines = metrics_file.read_text().strip().splitlines()
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["speaker_count"] == 3
    assert first["transcription_seconds"] == 12.5
    assert "timestamp" in first
