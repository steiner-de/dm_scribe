import asyncio
import io

import voice_handler


class FakeGuild:
    def __init__(self, guild_id):
        self.id = guild_id


class FakeChannel:
    def __init__(self, guild_id, name="general"):
        self.guild = FakeGuild(guild_id)
        self.name = name


class FakeAudioData:
    def __init__(self, data: bytes):
        self.file = io.BytesIO(data)


class FakeVoiceClient:
    """Stands in for py-cord's VoiceClient recording API (start_recording/
    stop_recording), which normally runs a background thread and schedules
    the finished-callback coroutine on the event loop once stopped."""

    def __init__(self, guild_id, fake_audio_data):
        self.channel = FakeChannel(guild_id)
        self.recording = False
        self._fake_audio_data = fake_audio_data
        self._sink = None
        self._callback = None
        self._callback_args = None

    def start_recording(self, sink, callback, *args, sync_start=False):
        self.recording = True
        sink.audio_data = self._fake_audio_data
        self._sink = sink
        self._callback = callback
        self._callback_args = args

    def stop_recording(self):
        self.recording = False
        asyncio.ensure_future(self._callback(self._sink, *self._callback_args))


def test_start_and_stop_recording_writes_per_speaker_wav_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def run():
        handler = voice_handler.VoiceHandler(bot=None)
        fake_audio = {
            111: FakeAudioData(b"\x00" * 3200),
            222: FakeAudioData(b"\x01" * 3200),
        }
        vc = FakeVoiceClient(guild_id=999, fake_audio_data=fake_audio)
        handler.voice_clients[999] = vc  # normally populated by join_voice_channel

        assert handler.start_recording(vc) is True
        assert handler.recording is True
        assert handler.start_recording(vc) is False  # already recording

        user_files = await handler.stop_recording(999)

        assert handler.recording is False
        assert set(user_files.keys()) == {"111", "222"}
        for path in user_files.values():
            assert (tmp_path / path).exists()

    asyncio.run(run())


def test_stop_recording_when_not_recording_returns_empty_dict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def run():
        handler = voice_handler.VoiceHandler(bot=None)
        result = await handler.stop_recording(guild_id=123)
        assert result == {}

    asyncio.run(run())
