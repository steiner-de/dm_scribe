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
- **`src/utils.py`** — `save_transcript_for_training`/`export_training_data` accumulate session
  transcripts as JSONL in `training_data/`, intended as future fine-tuning data (see
  `DND_LLM_GUIDE.md`). `export_training_data` is exposed via the (currently unimplemented in
  code) `/export_data` command mentioned in `README.md`.
- **`src/train_llm.py`** — scaffolding for fine-tuning a custom D&D LLM; not currently
  functional (targets a placeholder base model and has a `Trainer`/`TrainingArguments` mixup).
  Not wired into the bot — `summarize_with_llm` calls stock `mistral` via Ollama.
- **`src/config.py`** — all runtime config comes from environment variables (`.env`, loaded by
  `run.py`); see `.env.example` for the full list (`DISCORD_TOKEN`, `WHISPER_MODEL`, etc.).

### Known landmine

`pyproject.toml` lists `discord.py>=2.0.0` as a dependency even though the project fully
migrated to `py-cord` (`requirements.txt` pins `py-cord==2.7.2`). Both packages install into
the same `discord` namespace and conflict — don't add `discord.py` back, and prefer fixing
`pyproject.toml` to drop it rather than reintroducing it elsewhere.

### Release process

`.version` at the repo root is the single source of truth for the release version (see
`RELEASE_PROCESS.md`). `.github/workflows/release.yml` runs on push to `main`: lints with
flake8, runs the test suite, then tags and creates a GitHub release from `.version`. Bump
`.version` (and keep `pyproject.toml`'s version field in sync) as part of any PR meant to cut a
release.
