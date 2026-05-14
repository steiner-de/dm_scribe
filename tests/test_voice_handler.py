import asyncio
import os
import sys
import wave
from types import SimpleNamespace


class ClientException(Exception):
    pass


class FakeSink:
    def __init__(self, *, filters=None):
        self.filtered_users = []
        self.finished = False
        self.vc = None

    def init(self, vc):
        self.vc = vc


class FakeDecoder:
    SAMPLING_RATE = 48000
    CHANNELS = 2
    SAMPLE_SIZE = 4


sys.modules.setdefault(
    "discord",
    SimpleNamespace(
        VoiceChannel=object,
        ClientException=ClientException,
        sinks=SimpleNamespace(Sink=FakeSink),
        opus=SimpleNamespace(Decoder=FakeDecoder),
    ),
)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import voice_handler
from voice_handler import CombinedPCMSink, VoiceHandler


class FakeVoiceClient:
    def __init__(self, guild, channel, connected=True):
        self.guild = guild
        self.channel = channel
        self.connected = connected
        self.moved_to = None
        self.disconnect_calls = []
        self.recording_sink = None
        self.recording_callback = None
        self.stop_recording_calls = 0

    def is_connected(self):
        return self.connected

    async def move_to(self, channel):
        self.channel = channel
        self.moved_to = channel

    async def disconnect(self, *, force=False):
        self.connected = False
        self.disconnect_calls.append(force)

    def start_recording(self, sink, callback):
        self.recording_sink = sink
        self.recording_callback = callback

    def stop_recording(self):
        self.stop_recording_calls += 1
        if self.recording_callback:
            self.recording_callback(None)


class FakeChannel:
    def __init__(self, guild, name, voice_client=None, connect_error=None):
        self.guild = guild
        self.name = name
        self.voice_client = voice_client
        self.connect_error = connect_error
        self.connect_calls = 0

    async def connect(self, **kwargs):
        self.connect_calls += 1
        if self.connect_error:
            error = self.connect_error
            if isinstance(error, list):
                error = error.pop(0)
            if error:
                raise error
        return self.voice_client


def test_join_voice_channel_reuses_existing_client_and_moves_channels():
    guild = SimpleNamespace(id=123)
    old_channel = FakeChannel(guild, "old")
    new_channel = FakeChannel(guild, "new")
    voice_client = FakeVoiceClient(guild, old_channel)
    bot = SimpleNamespace(voice_clients=[])
    handler = VoiceHandler(bot)
    handler.voice_clients[guild.id] = voice_client

    joined = asyncio.run(handler.join_voice_channel(new_channel))

    assert joined is voice_client
    assert voice_client.moved_to is new_channel
    assert handler.channel_name == "new"


def test_join_voice_channel_recovers_existing_client_after_already_connected_error():
    guild = SimpleNamespace(id=123)
    channel = FakeChannel(
        guild,
        "table",
        connect_error=ClientException("Already connected to a voice channel."),
    )
    voice_client = FakeVoiceClient(guild, channel)
    bot = SimpleNamespace(voice_clients=[voice_client])
    handler = VoiceHandler(bot)

    joined = asyncio.run(handler.join_voice_channel(channel))

    assert joined is voice_client
    assert handler.voice_clients[guild.id] is voice_client
    assert handler.channel_name == "table"


def test_join_voice_channel_replaces_stale_registered_client():
    guild = SimpleNamespace(id=123)
    stale_client = FakeVoiceClient(guild, None, connected=False)
    fresh_client = FakeVoiceClient(guild, None)
    channel = FakeChannel(guild, "table", voice_client=fresh_client)
    bot = SimpleNamespace(voice_clients=[stale_client])
    handler = VoiceHandler(bot)

    joined = asyncio.run(handler.join_voice_channel(channel))

    assert joined is fresh_client
    assert stale_client.disconnect_calls == [True]
    assert channel.connect_calls == 1
    assert handler.voice_clients[guild.id] is fresh_client
    assert handler.channel_name == "table"


def test_join_voice_channel_retries_after_already_connected_stale_client():
    guild = SimpleNamespace(id=123)
    stale_client = FakeVoiceClient(guild, None, connected=False)
    fresh_client = FakeVoiceClient(guild, None)
    channel = FakeChannel(
        guild,
        "table",
        voice_client=fresh_client,
        connect_error=[ClientException("Already connected to a voice channel."), None],
    )
    bot = SimpleNamespace(voice_clients=[stale_client])
    handler = VoiceHandler(bot)

    joined = asyncio.run(handler.join_voice_channel(channel))

    assert joined is fresh_client
    assert stale_client.disconnect_calls == [True]
    assert channel.connect_calls == 2
    assert handler.voice_clients[guild.id] is fresh_client


def test_join_voice_channel_cleans_up_failed_partial_connection():
    guild = SimpleNamespace(id=123)
    partial_client = FakeVoiceClient(guild, None, connected=False)
    channel = FakeChannel(guild, "table", connect_error=RuntimeError("voice failed"))
    bot = SimpleNamespace(voice_clients=[partial_client])
    handler = VoiceHandler(bot)

    try:
        asyncio.run(handler.join_voice_channel(channel))
    except RuntimeError as exc:
        assert str(exc) == "voice failed"
    else:
        raise AssertionError("Expected RuntimeError")

    assert partial_client.disconnect_calls == [True]
    assert handler.voice_clients == {}


def test_leave_voice_channel_disconnects_discovered_client():
    guild = SimpleNamespace(id=123)
    channel = FakeChannel(guild, "table")
    voice_client = FakeVoiceClient(guild, channel)
    bot = SimpleNamespace(voice_clients=[voice_client])
    handler = VoiceHandler(bot)

    asyncio.run(handler.leave_voice_channel(guild.id))

    assert voice_client.disconnect_calls == [True]
    assert handler.voice_clients == {}
    assert handler.voice_client is None
    assert handler.channel_name is None


def test_leave_voice_channel_disconnects_stale_tracked_client():
    guild = SimpleNamespace(id=123)
    channel = FakeChannel(guild, "table")
    voice_client = FakeVoiceClient(guild, channel, connected=False)
    bot = SimpleNamespace(voice_clients=[])
    handler = VoiceHandler(bot)
    handler.voice_clients[guild.id] = voice_client

    asyncio.run(handler.leave_voice_channel(guild.id))

    assert voice_client.disconnect_calls == [True]
    assert handler.voice_clients == {}


def test_disconnect_all_disconnects_tracked_and_bot_clients_once():
    guild = SimpleNamespace(id=123)
    other_guild = SimpleNamespace(id=456)
    tracked_client = FakeVoiceClient(guild, FakeChannel(guild, "table"))
    bot_client = FakeVoiceClient(other_guild, FakeChannel(other_guild, "side table"))
    bot = SimpleNamespace(voice_clients=[tracked_client, bot_client])
    handler = VoiceHandler(bot)
    handler.voice_clients[guild.id] = tracked_client
    handler.voice_client = tracked_client
    handler.channel_name = "table"
    handler.recording = True

    asyncio.run(handler.disconnect_all())

    assert tracked_client.disconnect_calls == [True]
    assert bot_client.disconnect_calls == [True]
    assert handler.voice_clients == {}
    assert handler.voice_client is None
    assert handler.channel_name is None
    assert handler.recording is False


def test_start_recording_uses_current_pycord_recording_api():
    guild = SimpleNamespace(id=123)
    voice_client = FakeVoiceClient(guild, FakeChannel(guild, "table"))
    handler = VoiceHandler(SimpleNamespace(voice_clients=[]))

    started = handler.start_recording(voice_client)

    assert started is True
    assert handler.recording is True
    assert voice_client.recording_sink is handler.recording_sink
    assert handler.recording_sink.vc is voice_client


def test_combined_pcm_sink_matches_pycord_receive_router_contract():
    sink = CombinedPCMSink()

    assert sink.__sink_listeners__ == ()
    assert sink.sink_listeners == ()
    assert sink.walk_children() == ()
    assert sink.is_opus() is False


def test_corrupt_opus_frame_patch_replaces_decode_errors(monkeypatch):
    class FakeOpusError(Exception):
        pass

    class FakePacketDecoder:
        def __init__(self):
            self._decoder = SimpleNamespace(decode=lambda data, fec=False: b"concealed")

        def _decode_packet(self, packet):
            raise FakeOpusError("corrupted stream")

    fake_opus = SimpleNamespace(
        PacketDecoder=FakePacketDecoder,
        OpusError=FakeOpusError,
        Decoder=FakeDecoder,
    )
    monkeypatch.setattr(voice_handler.discord, "opus", fake_opus)

    assert voice_handler.patch_pycord_corrupt_opus_frames() is True
    packet = object()
    decoder = FakePacketDecoder()

    assert decoder._decode_packet(packet) == (packet, b"concealed")


def test_stop_recording_writes_combined_pcm_to_wav(monkeypatch):
    tmp_dir = os.path.abspath(os.path.join(".pytest_tmp", "voice_handler_recording"))
    os.makedirs(tmp_dir, exist_ok=True)
    monkeypatch.chdir(tmp_dir)
    guild = SimpleNamespace(id=123)
    voice_client = FakeVoiceClient(guild, FakeChannel(guild, "table"))
    handler = VoiceHandler(SimpleNamespace(voice_clients=[]))
    handler.start_recording(voice_client)

    handler.recording_sink.write(SimpleNamespace(pcm=b"\x00\x00\x00\x00"), None)
    filename = handler.stop_recording()

    assert filename == "recordings/recording.wav"
    assert voice_client.stop_recording_calls == 1
    assert handler.recording is False

    with wave.open(filename, "rb") as wf:
        assert wf.getframerate() == 48000
        assert wf.getnchannels() == 2
        assert wf.getsampwidth() == 2
        assert wf.readframes(wf.getnframes()) == b"\x00\x00\x00\x00"
