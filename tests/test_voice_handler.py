import os

import voice_handler


def test_stop_recording_writes_wave_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    handler = voice_handler.VoiceHandler(bot=None)
    handler.recording = True
    handler.audio_frames = [b"\x00" * 3200]

    output_path = handler.stop_recording(filename="test.wav")

    assert output_path == os.path.join("recordings", "test.wav")
    assert (tmp_path / "recordings" / "test.wav").exists()
