"""
Handles voice channel connections and audio capture.
"""

import discord
import asyncio
from config import SAMPLE_RATE, CHANNELS

class VoiceHandler:
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}

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