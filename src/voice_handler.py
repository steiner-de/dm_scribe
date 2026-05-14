"""
Handles voice channel connections and audio capture using py-cord.
Streaming audio directly to file with minimal memory overhead.
"""

import discord
import wave
import os
import asyncio
import io
import logging


_log = logging.getLogger(__name__)


def patch_pycord_corrupt_opus_frames():
    """Keep py-cord's voice reader alive when DAVE yields a bad Opus frame."""
    opus = getattr(discord, "opus", None)
    packet_decoder = getattr(opus, "PacketDecoder", None)
    opus_error = getattr(opus, "OpusError", None)
    if packet_decoder is None or opus_error is None:
        return False

    if getattr(packet_decoder, "_dm_scribe_corrupt_frame_guard", False):
        return True

    original_decode_packet = packet_decoder._decode_packet

    def decode_packet_with_corrupt_frame_guard(self, packet):
        try:
            return original_decode_packet(self, packet)
        except opus_error as exc:
            _log.debug("Replacing corrupt Opus frame with silence.", exc_info=exc)
            decoder = getattr(self, "_decoder", None)
            if decoder is not None:
                try:
                    return packet, decoder.decode(None, fec=False)
                except Exception:
                    pass
            return packet, _silence_pcm()

    packet_decoder._dm_scribe_original_decode_packet = original_decode_packet
    packet_decoder._decode_packet = decode_packet_with_corrupt_frame_guard
    packet_decoder._dm_scribe_corrupt_frame_guard = True
    return True


def _silence_pcm():
    decoder = getattr(discord.opus, "Decoder", None)
    frame_size = getattr(decoder, "SAMPLES_PER_FRAME", 960)
    sample_size = getattr(decoder, "SAMPLE_SIZE", 4)
    return b"\x00" * frame_size * sample_size


class CombinedPCMSink(discord.sinks.Sink):
    """Collect decoded PCM packets into a single chronological stream."""

    encoding = "pcm"
    __sink_listeners__ = ()
    sink_listeners = ()

    def __init__(self, *, filters=None):
        super().__init__(filters=filters)
        self.file = io.BytesIO()

    def is_opus(self):
        return False

    def walk_children(self):
        return ()

    def write(self, data, user):
        if self.finished:
            return
        if self.filtered_users and user not in self.filtered_users:
            return

        pcm = getattr(data, "pcm", data)
        if pcm:
            self.file.write(pcm)

    def cleanup(self):
        self.finished = True
        self.file.seek(0)

    def format_audio(self, audio):
        return


class VoiceHandler:
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.recording = False
        self.audio_frames = []
        self.voice_client = None
        self.channel_name = None
        self._join_locks = {}
        self.recording_sink = None
        self.recording_error = None

    async def join_voice_channel(self, channel: discord.VoiceChannel):
        """Join a voice channel using py-cord."""
        guild_id = channel.guild.id
        lock = self._join_locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            return await self._join_voice_channel(channel)

    async def _join_voice_channel(self, channel: discord.VoiceChannel):
        guild_id = channel.guild.id
        voice_client = self.get_voice_client(guild_id)
        if voice_client:
            if getattr(voice_client, "channel", None) != channel:
                await voice_client.move_to(channel)
            self.channel_name = channel.name
            return voice_client

        await self._disconnect_stale_voice_client(guild_id)

        try:
            voice_client = await channel.connect(timeout=15.0, reconnect=False)
        except discord.ClientException as e:
            if "Already connected" not in str(e):
                await self._cleanup_guild_voice_client(guild_id)
                raise
            voice_client = self._find_guild_voice_client(channel.guild.id)
            if voice_client and voice_client.is_connected():
                self.voice_clients[guild_id] = voice_client
            else:
                await self._cleanup_guild_voice_client(guild_id)
                try:
                    voice_client = await channel.connect(timeout=15.0, reconnect=False)
                except Exception:
                    await self._cleanup_guild_voice_client(guild_id)
                    raise
        except Exception:
            await self._cleanup_guild_voice_client(guild_id)
            raise

        if voice_client is None or not voice_client.is_connected():
            if voice_client:
                await self._disconnect_voice_client(voice_client)
            await self._cleanup_guild_voice_client(guild_id)
            raise RuntimeError("Failed to connect to voice channel")

        self.voice_clients[guild_id] = voice_client
        self.channel_name = channel.name
        return voice_client

    async def _disconnect_stale_voice_client(self, guild_id):
        voice_client = self.voice_clients.get(guild_id) or self._find_guild_voice_client(guild_id)
        if voice_client and not voice_client.is_connected():
            await self._disconnect_voice_client(voice_client)
            self.voice_clients.pop(guild_id, None)

    async def _cleanup_guild_voice_client(self, guild_id):
        voice_client = self.voice_clients.pop(guild_id, None) or self._find_guild_voice_client(
            guild_id
        )
        if voice_client:
            try:
                await self._disconnect_voice_client(voice_client)
            except Exception:
                raise

    async def leave_voice_channel(self, guild_id):
        """Leave a voice channel."""
        voice_client = self.voice_clients.get(guild_id) or self._find_guild_voice_client(guild_id)
        if voice_client:
            await self._disconnect_voice_client(voice_client)
        self.voice_clients.pop(guild_id, None)
        if self.voice_client is voice_client:
            self.voice_client = None
        if not self.voice_clients:
            self.channel_name = None
        return voice_client is not None

    async def disconnect_all(self):
        """Disconnect every known voice client before the bot shuts down."""
        voice_clients = list(self.voice_clients.values())
        for voice_client in getattr(self.bot, "voice_clients", []):
            if voice_client not in voice_clients:
                voice_clients.append(voice_client)

        for voice_client in voice_clients:
            await self._disconnect_voice_client(voice_client)

        self.voice_clients.clear()
        self.voice_client = None
        self.channel_name = None
        self.recording = False

    async def _disconnect_voice_client(self, voice_client):
        if not voice_client:
            return
        try:
            try:
                await voice_client.disconnect(force=True)
            except TypeError:
                await voice_client.disconnect()
        finally:
            self._forget_bot_voice_client(voice_client)

    def _forget_bot_voice_client(self, voice_client):
        voice_clients = getattr(self.bot, "voice_clients", None)
        if isinstance(voice_clients, list) and voice_client in voice_clients:
            voice_clients.remove(voice_client)

    def get_voice_client(self, guild_id):
        """Get the voice client for a guild."""
        voice_client = self.voice_clients.get(guild_id) or self._find_guild_voice_client(guild_id)
        if voice_client and voice_client.is_connected():
            self.voice_clients[guild_id] = voice_client
            return voice_client
        self.voice_clients.pop(guild_id, None)
        return None

    def _find_guild_voice_client(self, guild_id):
        for voice_client in getattr(self.bot, "voice_clients", []):
            guild = getattr(voice_client, "guild", None)
            if guild and guild.id == guild_id:
                return voice_client
        return None

    def start_recording(self, voice_client):
        """Start recording audio from the voice client."""
        if self.recording:
            return False

        patch_pycord_corrupt_opus_frames()
        sink = CombinedPCMSink()
        sink.init(voice_client)
        voice_client.start_recording(sink, self._on_recording_finished)

        self.voice_client = voice_client
        self.recording_sink = sink
        self.recording_error = None
        self.recording = True
        os.makedirs("recordings", exist_ok=True)
        return True

    def _on_recording_finished(self, error):
        self.recording_error = error

    def stop_recording(self, filename="recording.wav"):
        """Stop recording and save the file."""
        if not self.recording:
            return None

        self.recording = False
        os.makedirs("recordings", exist_ok=True)
        final_path = f"recordings/{filename}"

        voice_client = self.voice_client
        sink = self.recording_sink
        self.voice_client = None
        self.recording_sink = None

        if voice_client:
            try:
                voice_client.stop_recording()
            except Exception as e:
                self.recording_error = e

        if not sink:
            return None

        sink.cleanup()
        pcm = sink.file.read()
        if not pcm:
            return None

        sample_rate, channels, sample_width = self._recording_wave_params()
        with wave.open(final_path, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)

        return final_path

    def _recording_wave_params(self):
        decoder = getattr(discord.opus, "Decoder", None)
        sample_rate = getattr(decoder, "SAMPLING_RATE", 48000)
        channels = getattr(decoder, "CHANNELS", 2)
        sample_size = getattr(decoder, "SAMPLE_SIZE", channels * 2)
        sample_width = sample_size // channels
        return sample_rate, channels, sample_width
