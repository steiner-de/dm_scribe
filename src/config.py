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

# faster-whisper device/precision. "auto" uses CUDA if a GPU + working CTranslate2
# CUDA build are available, otherwise falls back to CPU. On a CUDA machine, consider
# WHISPER_COMPUTE_TYPE=float16 for a real speed/quality win over the CPU-safe "int8" default.
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# Base URL of the Ollama server. Defaults to local, but can point at a remote
# Ollama instance (e.g. a GPU server reached over Tailscale/SSH tunnel) so that
# scripts run from a different machine (src/ingest_lore.py, src/ask.py) can use
# the same LLM/embedding model without needing their own local Ollama.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Ollama model used for session summarization. Swap to a fine-tuned model's
# name (see DND_LLM_GUIDE.md / src/package_for_ollama.py) once one exists.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

# Ollama embedding model used to index/search past session summaries.
# Pull it once with: ollama pull nomic-embed-text
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

# Local, file-based vector store for past session summaries (RAG + /recall).
VECTOR_STORE_DIR = os.getenv("VECTOR_STORE_DIR", "vector_store")

# If set, connect to a networked Chroma server (`chroma run`) instead of the
# local embedded store -- needed for src/ingest_lore.py / src/ask.py to reach
# the same vector store from a different machine than the bot. Leave unset to
# keep using the local embedded store (the default, unchanged behavior).
CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

# Audio settings
AUDIO_FORMAT = "wav"
SAMPLE_RATE = 16000
CHANNELS = 1

# Output settings
DEFAULT_TEXT_CHANNEL = os.getenv("DEFAULT_TEXT_CHANNEL_ID")

# Bot settings
COMMAND_PREFIX = "!"
BOT_ACTIVITY = (
    "Fly Scribe: A fly-on-the-wall voice transcriber, "
    "note keeper, and lore builder for D&D sessions"
)
