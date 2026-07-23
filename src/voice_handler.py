"""
Handles voice channel connections and audio capture using py-cord.

Recording uses py-cord's Sink API, which gives each speaker their own
audio track (keyed by Discord user ID) rather than mixing everyone down
into a single file. That per-speaker separation is what lets transcripts
be attributed to the correct character without needing diarization.
"""

import asyncio
import logging
import os
from datetime import datetime

import discord
from discord.sinks import RecordingException, WaveSink

logger = logging.getLogger(__name__)

RECORDINGS_DIR = "recordings"


class VoiceHandler:
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.recording_guilds = set()
        self.channel_name = None
        self._finished_futures = {}

    async def join_voice_channel(self, channel: discord.VoiceChannel):
        """Join a voice channel using py-cord."""
        guild_id = channel.guild.id
        existing = self.voice_clients.get(guild_id)
        if existing:
            if existing.is_connected():
                return existing
            try:
                await existing.disconnect()
            except Exception:
                pass
            del self.voice_clients[guild_id]

        voice_client = await channel.connect()
        self.channel_name = channel.name

        if not voice_client.is_connected():
            raise Exception("Failed to connect to voice channel")

        self.voice_clients[guild_id] = voice_client
        return voice_client

    async def leave_voice_channel(self, guild_id):
        """Leave a voice channel, flushing any in-progress recording first
        so speaker audio is written to disk instead of orphaned mid-sink."""
        if guild_id in self.recording_guilds:
            await self.stop_recording(guild_id)
        if guild_id in self.voice_clients:
            await self.voice_clients[guild_id].disconnect()
            del self.voice_clients[guild_id]

    def get_voice_client(self, guild_id):
        """Get the voice client for a guild."""
        return self.voice_clients.get(guild_id)

    def is_recording(self, guild_id) -> bool:
        """Whether the given guild currently has an active recording."""
        return guild_id in self.recording_guilds

    def start_recording(self, voice_client) -> bool:
        """
        Start recording the voice channel, capturing each speaker's audio
        on its own track via py-cord's Sink API.
        """
        guild_id = voice_client.channel.guild.id
        if guild_id in self.recording_guilds:
            return False

        self.channel_name = voice_client.channel.name

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._finished_futures[guild_id] = future

        try:
            voice_client.start_recording(
                WaveSink(), self._on_recording_finished, guild_id, sync_start=True
            )
        except RecordingException as e:
            logger.error(f"Failed to start recording: {e}")
            del self._finished_futures[guild_id]
            return False

        self.recording_guilds.add(guild_id)
        return True

    async def _on_recording_finished(self, sink, guild_id):
        """
        py-cord invokes this once every speaker's audio has been flushed
        after stop_recording(). Writes one WAV file per speaker to disk.
        """
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        user_files = {}
        for user_id, audio in sink.audio_data.items():
            path = os.path.join(RECORDINGS_DIR, f"{guild_id}_{timestamp}_{user_id}.wav")
            try:
                with open(path, "wb") as f:
                    f.write(audio.file.read())
                user_files[str(user_id)] = path
            except OSError as e:
                logger.error(f"Failed to save recording for user {user_id}: {e}")

        future = self._finished_futures.pop(guild_id, None)
        if future and not future.done():
            future.set_result(user_files)

    async def stop_recording(self, guild_id) -> dict:
        """
        Stop recording and wait for py-cord to flush each speaker's audio
        to disk.

        Returns:
            dict: {discord_user_id (str): wav_file_path}
        """
        voice_client = self.voice_clients.get(guild_id)
        not_recording = (
            guild_id not in self.recording_guilds
            or voice_client is None
            or not voice_client.recording
        )
        if not_recording:
            self.recording_guilds.discard(guild_id)
            return {}

        future = self._finished_futures.get(guild_id)
        voice_client.stop_recording()
        self.recording_guilds.discard(guild_id)

        if future is None:
            return {}
        return await future
