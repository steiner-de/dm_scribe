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
  transcribes each speaker's isolated WAV with `faster-whisper` independently (`vad_filter=True`
  — required, since `sync_start=True` pads every speaker's track with silence to the full
  session length, so without VAD, transcription cost scales with session length × speaker
  count instead of actual talk time), then merges all segments across speakers by timestamp
  into one chronological, character-labeled transcript. `summarize_with_llm()` sends that
  transcript to Ollama (`OLLAMA_MODEL`, default `mistral`) for a lore/loot/plot summary, with
  an optional `prior_context` param for RAG (see `vector_store.py` below). `save_obsidian_note()`
  writes the summary as markdown to `obsidian_notes/`.
- **`src/utils.py`** — `save_transcript_for_training(transcript, summary, session_id,
  channel_name)` is called from `bot.py` after each session's summary is generated, saving both
  as one training example under `training_data/`. `export_training_data()` turns all saved
  examples into `exported_training_data.jsonl`, one `{"instruction": ..., "response": ...}` pair
  per session (records saved before summary-capture existed, transcript-only, are skipped).
  Exposed in Discord via the admin-only `/export_data` command in `bot.py`. Also has
  `get_wav_duration_seconds()` and `log_session_metrics()`, used by `bot.process_recording()`
  to append per-session cost/capacity data (speaker count, session duration, transcription
  and summarization wall-clock time, transcript/summary size) to `session_metrics.jsonl` —
  meant for measuring real hosting cost/throughput during playtesting, not user-facing.
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
- **`src/vector_store.py`** — `SessionVectorStore` wraps a Chroma collection with embeddings
  from Ollama's embedding model (`config.OLLAMA_EMBEDDING_MODEL`, default `nomic-embed-text`,
  reached via `config.OLLAMA_HOST`). Two client modes: embedded (`PersistentClient`, persisted
  under `config.VECTOR_STORE_DIR`, the default) or networked (`HttpClient`, used when
  `config.CHROMA_HOST` is set — this is what lets `src/ingest_lore.py`/`src/ask.py` reach the
  same store from a different machine than the bot; see `EXTERNAL_SERVER_SETUP.md`). Used three
  ways: (1) RAG — `bot._build_prior_context()` queries it before summarizing so
  `summarize_with_llm`'s `prior_context` param can give the LLM continuity with past sessions;
  (2) search — the `/recall` command queries it directly; (3) lore ingestion — `add_document()`
  is the generic entry point (`add_session()` is a thin wrapper over it for the session-summary
  case) used by `src/ingest_lore.py` to load arbitrary reference material in. `chunk_text()`
  splits long documents into embeddable pieces (packs whole paragraphs up to `max_chars`, hard-
  splits with overlap only when a single paragraph exceeds it). Every entry carries a `guild_id`
  metadata field and every query filters on it, so one server's data can't leak into another's.
  `add_document`/`query` both fail soft (return `False`/`[]`, never raise) so a missing/
  unreachable Ollama degrades gracefully instead of breaking `/stop`.
- **`src/ingest_lore.py`** — CLI to load homebrew lore/rulebook/reference text files into the
  vector store (chunked via `vector_store.chunk_text`), tagged `type: "lore"` and a `source`
  filename in metadata, distinguishing them from `type: "session"` entries. Chunk IDs are
  deterministic (`lore:{filename}:{index}`) so re-ingesting an unchanged file is a no-op upsert;
  note the docstring caveat about stale chunks if a file shrinks between runs.
- **`src/ask.py`** — CLI to ask a question against the vector store (sessions + lore) and get a
  synthesized answer: `ask()` retrieves relevant chunks via `SessionVectorStore.query`, then asks
  Ollama to answer using only that context. Same retrieve-then-generate shape as `/recall`, but
  `/recall` only surfaces raw matches — this synthesizes an actual answer.
- **`src/config.py`** — all runtime config comes from environment variables (`.env`, loaded by
  `run.py`); see `.env.example` for the full list (`DISCORD_TOKEN`, `WHISPER_MODEL`,
  `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_EMBEDDING_MODEL`, `VECTOR_STORE_DIR`, `CHROMA_HOST`,
  `CHROMA_PORT`, etc.). `OLLAMA_HOST` defaults to local but can point at a remote Ollama —
  `bot.start_ollama_server()` checks this (`_is_local_ollama_host()`) and refuses to try
  auto-starting a remote Ollama via a local subprocess.

### Known issues / planned work: multi-server (multi-guild) correctness

The bot currently only runs in one Discord server at a time in practice. An audit for
"what if this joins other servers" (2026-07-25) found real bugs that are latent with a
single guild but would misbehave the moment a second one is active — not just scaling
concerns. None of this is implemented yet; this is a plan for when it's picked up.

1. **`self.current_voice_client` in `bot.py` is a single bot-wide slot, not per-guild —
   the most serious one.** `/join`, `/leave`, `/inscribe`, and `/stop` all do
   `voice_client = self.current_voice_client or self.voice_handler.get_voice_client(ctx.guild.id)`.
   `self.current_voice_client` gets overwritten by whichever guild joined voice most
   recently, and is checked *before* the correct per-guild lookup. Concretely: Guild A
   joins voice, then Guild B joins voice (`self.current_voice_client` now points at B's
   client); if Guild A's DM then runs `/inscribe`, this hands *Guild B's* voice client
   into `start_recording()`, which derives which guild to record under from that
   client's channel — Guild A's command could end up recording Guild B's voice channel.
   Fix: delete `self.current_voice_client` entirely; `voice_handler.get_voice_client(guild.id)`
   is already correct and sufficient on its own.

2. **`character_map.json` is global, keyed only by `user_id`**
   (`{user_id: {name, class, species, gender, ...}}`) — `assign_character`, `assign_dm`,
   and `remove_character` in `bot.py` all write to it with no `guild_id` nesting. A
   player in two different servers running this bot collides on the same entry. Needs
   to become `{guild_id: {user_id: {...}}}`, with every character command in `bot.py`
   threading `ctx.guild.id` through.

3. **`/remove_all_characters` wipes the entire map for every server** — `self.character_map = {}`
   isn't scoped to `ctx.guild`, so an admin in *any* server running this nukes every
   other server's character assignments too. Needs to become guild-scoped once (2) lands.

4. **Training data mixes all guilds together.** `save_transcript_for_training` (see
   `utils.py` above) doesn't record `guild_id` at all, and `export_training_data()`/the
   `/export_data` command export everything unfiltered — any server admin running
   `/export_data` currently gets every other customer's session transcripts. Needs a
   `guild_id` field added to saved training records and `/export_data` filtered to the
   invoking guild.

**Already fine, built guild-scoped from the start:** `voice_handler.py`
(`voice_clients`/`recording_guilds` keyed by `guild_id`), `notes_channel_map.json`
(already `{guild_id: channel_id}`), and `vector_store.py` (every entry carries
`guild_id`, every query filters on it).

**Migration note:** there's no reliable way to auto-migrate an existing
`character_map.json` from the old flat format into the new `{guild_id: {...}}` schema,
since it never recorded which guild each assignment belonged to. Re-running
`/assign_character` after the change is the expected path, not a scripted migration.

### Release process

`.version` at the repo root is the single source of truth for the release version (see
`RELEASE_PROCESS.md`). `.github/workflows/release.yml` runs on push to `main`: lints with
flake8, runs the test suite, then tags and creates a GitHub release from `.version`. Bump
`.version` (and keep `pyproject.toml`'s version field in sync) as part of any PR meant to cut a
release.
