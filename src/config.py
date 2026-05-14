"""
Configuration settings for the Discord bot.
"""

import os

# Discord Bot Token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Transcription settings
TRANSCRIPTION_SERVICE = os.getenv(
    "TRANSCRIPTION_SERVICE", "faster-whisper"
)  # 'faster-whisper', 'google', etc.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")  # tiny, base, small, medium, large

# Audio settings
AUDIO_FORMAT = "wav"
SAMPLE_RATE = 16000
CHANNELS = 1

# Output settings
DEFAULT_TEXT_CHANNEL = os.getenv("DEFAULT_TEXT_CHANNEL_ID")
VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "vector_db_data")
DISCORD_GUILD_IDS = [
    int(guild_id.strip())
    for guild_id in os.getenv("DISCORD_GUILD_IDS", "").split(",")
    if guild_id.strip()
]

# Bot settings
COMMAND_PREFIX = "!"
BOT_ACTIVITY = ("Fly Scribe: A fly-on-the-wall voice transcriber, "
                    "note keeper, and lore builder for D&D sessions"
                )
