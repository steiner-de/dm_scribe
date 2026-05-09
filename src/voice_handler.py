"""
Handles voice channel connections and audio capture.
"""

import discord
import pyaudio
import wave
from config import SAMPLE_RATE, CHANNELS


class VoiceHandler:
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.recording = False
        self.audio_frames = []
        self.audio = pyaudio.PyAudio()

    async def join_voice_channel(self, channel: discord.VoiceChannel):
        """Join a voice channel and start listening."""
        if channel.guild.id in self.voice_clients:
            return self.voice_clients[channel.guild.id]

        voice_client = await channel.connect()
        self.voice_clients[channel.guild.id] = voice_client

        # Start listening to audio
        voice_client.listen(discord.VoiceClient.listen)

        return voice_client

    async def leave_voice_channel(self, guild_id):
        """Leave a voice channel."""
        if guild_id in self.voice_clients:
            await self.voice_clients[guild_id].disconnect()
            del self.voice_clients[guild_id]

    def get_voice_client(self, guild_id):
        """Get the voice client for a guild."""
        return self.voice_clients.get(guild_id)

    def start_recording(self, voice_client):
        """Start recording audio from the voice client."""
        if self.recording:
            return False
        self.recording = True
        self.audio_frames = []

        # Note: For simplicity, we're not implementing real-time audio capture here.
        # In a full implementation, you'd hook into voice_client.listen or use a sink.
        # For now, this is a placeholder.
        return True

    def stop_recording(self, filename="recording.wav"):
        """Stop recording and save to file."""
        if not self.recording:
            return None
        self.recording = False

        # Save frames to WAV file
        wf = wave.open(filename, "wb")
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(self.audio_frames))
        wf.close()

        return filename
