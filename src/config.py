"""
Configuration settings for the Discord bot.
"""

import os

# Discord Bot Token
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Transcription settings
TRANSCRIPTION_SERVICE = os.getenv('TRANSCRIPTION_SERVICE', 'whisper')  # 'whisper', 'google', etc.
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'base')  # tiny, base, small, medium, large

# Audio settings
AUDIO_FORMAT = 'wav'
SAMPLE_RATE = 16000
CHANNELS = 1

# Output settings
DEFAULT_TEXT_CHANNEL = os.getenv('DEFAULT_TEXT_CHANNEL_ID')

# Bot settings
COMMAND_PREFIX = '!'
BOT_ACTIVITY = "Transcribing voice calls for D&D sessions"