"""
Handles voice channel connections and audio capture using py-cord.
Streaming audio directly to file with minimal memory overhead.
"""

import discord
import wave
import os
from config import SAMPLE_RATE, CHANNELS


class VoiceHandler:
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.recording = False
        self.audio_frames = []
        self.voice_client = None
        self.channel_name = None

    async def join_voice_channel(self, channel: discord.VoiceChannel):
        """Join a voice channel using py-cord."""
        if channel.guild.id in self.voice_clients:
            return self.voice_clients[channel.guild.id]

        voice_client = await channel.connect()
        self.channel_name = channel.name

        if not voice_client.is_connected():
            raise Exception("Failed to connect to voice channel")

        self.voice_clients[channel.guild.id] = voice_client
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
        # Async method description to record audio from the voice client
        @voice_client.listen(discord.sink)
        async def on_audio_packet(self, packet):
            """Handle incoming audio packets."""
            if self.recording:
                # Add audio chunks to frames list
                self.audio_frames.append(packet.data) 
        """Start recording audio from the voice client."""
        if self.recording:
            return False

        self.recording = True
        self.audio_frames = []
        self.voice_client = voice_client
        voice_client.listen(discord.sinks.WaveSink(sample_rate=16000,
                                                   channels=self.channel_name))
        os.makedirs("recordings", exist_ok=True)
        return True

    def stop_recording(self, filename="recording.wav"):
        """Stop recording and save the file."""
        if not self.recording:
            return None

        self.recording = False
        recordings_dir = os.path.join("recordings")
        os.makedirs(recordings_dir, exist_ok=True)
        final_path = os.path.join(recordings_dir, filename)

        with wave.open(final_path, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(self.audio_frames))

        return final_path
