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

# Ollama model used for session summarization. Swap to a fine-tuned model's
# name (see DND_LLM_GUIDE.md / src/package_for_ollama.py) once one exists.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

# Ollama embedding model used to index/search past session summaries.
# Pull it once with: ollama pull nomic-embed-text
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

# Local, file-based vector store for past session summaries (RAG + /recall).
VECTOR_STORE_DIR = os.getenv("VECTOR_STORE_DIR", "vector_store")

# Audio settings
AUDIO_FORMAT = "wav"
SAMPLE_RATE = 16000
CHANNELS = 1

# Output settings
DEFAULT_TEXT_CHANNEL = os.getenv("DEFAULT_TEXT_CHANNEL_ID")

# Bot settings
COMMAND_PREFIX = "!"
BOT_ACTIVITY = ("Fly Scribe: A fly-on-the-wall voice transcriber, "
                    "note keeper, and lore builder for D&D sessions"
                )
