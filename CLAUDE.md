# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Discord bot ("Fly Scribe") that joins a voice channel during a D&D session, records each
speaker's audio separately, transcribes it locally with `faster-whisper`, summarizes the
session with a local LLM via Ollama, and posts the summary to Discord + saves it as an
Obsidian markdown note. See `README.md` for the full command reference and setup steps, and
`DND_LLM_GUIDE.md` for the (currently unimplemented) plan to fine-tune a custom D&D LLM.

## Commands

This project uses `uv` as its package manager (`pyproject.toml` + `uv.lock`), but a
`requirements.txt` is also kept in sync for plain-`pip` installs.

```bash
# Install deps
uv sync
# or: pip install -r requirements.txt

# Run the bot (loads .env, needs DISCORD_TOKEN set)
python run.py
# or: uv run python run.py

# Run the full test suite — note the `--extra dev` flag is required,
# plain `uv run pytest` will fail with "program not found" because
# pytest/black/flake8 live in the `dev` optional-dependency group.
uv run --extra dev pytest tests/ -q

# Run a single test
uv run --extra dev pytest tests/test_transcriber.py::test_transcribe_speakers_merges_by_time_and_labels_characters -q

# Lint / format
uv run --extra dev black src/ tests/ run.py
uv run --extra dev flake8 src/ tests/ run.py
uv run --extra dev ruff check src/ tests/ run.py
```

Fine-tuning (`train_llm.py`, `package_for_ollama.py`) needs a separate extras group — it
pulls in `peft`/`bitsandbytes`/`trl` on top of the `transformers`/`torch`/`datasets` already
required by the bot, and needs a CUDA GPU to actually run:

```bash
uv sync --extra train
```

Ollama must be installed and reachable at `http://localhost:11434` for summarization to work
(`ollama pull mistral` once, then `ollama serve`). `bot.py` will attempt to auto-start it if
it's not running when `/stop` is used.

There is no `pytest-asyncio` dependency. Tests that exercise async code (e.g.
`tests/test_voice_handler.py`) wrap an inner `async def run(): ...` and drive it with
`asyncio.run(run())` rather than using `async def test_...`.

## Architecture

- **`run.py`** — entry point; loads `.env`, puts `src/` on `sys.path`, calls `bot.main()`.
- **`src/bot.py`** — `TranscriberBot` wraps a `discord.Bot` (py-cord) and owns all slash
  commands, plus the persisted JSON state: `character_map.json` (Discord user ID → character
  name/class/species/gender) and `notes_channel_map.json` (guild ID → channel ID for posting
  summaries). `process_recording()` is the orchestration point that chains
  transcription → summarization → Obsidian note → Discord post after `/stop`.
- **`src/voice_handler.py`** — `VoiceHandler` manages joining/leaving voice channels and
  recording. Recording uses py-cord's `Sink` API (`vc.start_recording(WaveSink(), callback,
  sync_start=True)`), which gives **each speaker their own audio track** keyed by Discord user
  ID — this is what makes correct per-character transcript attribution possible without
  diarization. `start_recording`/`stop_recording` are async: py-cord flushes each user's audio
  on a background thread and schedules the finished-callback coroutine on the event loop, so
  `stop_recording(guild_id)` awaits a future that the callback resolves once every speaker's
  WAV has been written to `recordings/`. `sync_start=True` is what keeps all speakers' tracks
  aligned to the same session start time — required for the chronological merge in
  `transcriber.py` to produce correctly-ordered dialogue.
- **`src/transcriber.py`** — `Transcriber.transcribe_speakers(user_files, character_map, ...)`
  transcribes each speaker's isolated WAV with `faster-whisper` independently, then merges all
  segments across speakers by timestamp into one chronological, character-labeled transcript.
  `summarize_with_llm()` sends that transcript to Ollama (`mistral` model) for a lore/loot/plot
  summary. `save_obsidian_note()` writes the summary as markdown to `obsidian_notes/`.
- **`src/utils.py`** — `save_transcript_for_training(transcript, summary, session_id,
  channel_name)` is called from `bot.py` after each session's summary is generated, saving both
  as one training example under `training_data/`. `export_training_data()` turns all saved
  examples into `exported_training_data.jsonl`, one `{"instruction": ..., "response": ...}` pair
  per session (records saved before summary-capture existed, transcript-only, are skipped).
  Exposed in Discord via the admin-only `/export_data` command in `bot.py`.
- **`src/train_llm.py`** — LoRA/QLoRA fine-tuning script (via `peft`/`trl`) that trains a
  `mistralai/Mistral-7B-Instruct-v0.3`-based model on `exported_training_data.jsonl`. Heavy ML
  imports are deferred inside functions so `--help` and the pure data-loading helpers
  (`format_example`, `load_training_dataset`, tested in `tests/test_train_llm.py`) work without
  the `train` extras installed. Needs a CUDA GPU to actually run training.
- **`src/package_for_ollama.py`** — merges a LoRA adapter produced by `train_llm.py` into its
  base model and writes an Ollama `Modelfile`; prints the remaining GGUF-conversion and
  `ollama create` steps (not automated — depends on llama.cpp, not a project dependency). The
  resulting model becomes a drop-in swap: set `OLLAMA_MODEL=<name>` in `.env` and
  `transcriber.summarize_with_llm` picks it up with no code changes.
- **`src/config.py`** — all runtime config comes from environment variables (`.env`, loaded by
  `run.py`); see `.env.example` for the full list (`DISCORD_TOKEN`, `WHISPER_MODEL`,
  `OLLAMA_MODEL`, etc.).

### Release process

`.version` at the repo root is the single source of truth for the release version (see
`RELEASE_PROCESS.md`). `.github/workflows/release.yml` runs on push to `main`: lints with
flake8, runs the test suite, then tags and creates a GitHub release from `.version`. Bump
`.version` (and keep `pyproject.toml`'s version field in sync) as part of any PR meant to cut a
release.
