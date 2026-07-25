# External Server Setup

This documents porting the bot from a local Windows dev machine to a dedicated,
always-on Linux server (an idle desktop with an NVIDIA GPU) for playtesting and,
longer-term, hosting. It covers the code changes that made this possible and the
deployment steps to actually do it.

## Overview

The chosen architecture is **whole bot on the server**: the Discord bot process,
Ollama (LLM + embeddings), the Chroma vector store, and faster-whisper transcription
all run together on the one machine. Discord bots only need outbound internet — no
inbound ports or public IP required — so this is a plain redeploy, not a network
service split. (A split architecture — bot process elsewhere, only Ollama/transcription
on the server — was considered and rejected for now: Ollama is already an HTTP service
so that half is easy, but faster-whisper runs in-process today and would need a new
transcription API server built from scratch. Revisit only if there's a concrete reason
to decouple them later.)

Linux was chosen over staying on Windows for this box because it removes real friction
(see the Opus fix below), has more mature Ollama/CUDA support, and gives a proper
always-on service story via systemd. It also matches what real cloud hosting
(e.g. a Hetzner/DigitalOcean VM) would look like later, so testing here now avoids
surprises if this project moves to paid hosting.

## Code changes made to support this

### 1. Opus loading was silently broken on Linux

`bot.py`'s `ensure_opus_loaded()` only tried Windows DLL filenames
(`libopus-0.dll`, `opus.dll`, `libopus.dll`) via a direct library-load call. None of
those resolve on Linux. py-cord has a working cross-platform lookup
(`ctypes.util.find_library("opus")`, used internally by `discord.opus._load_default()`),
but nothing in this codebase called it.

Fixed: on non-Windows platforms, `ensure_opus_loaded()` now tries
`ctypes.util.find_library("opus")` first, before falling through to the
Windows-specific candidates. Once `libopus0` is installed via `apt`, voice will load
correctly.

### 2. faster-whisper was hardcoded to CPU

`Transcriber.__init__` previously did:
```python
self.model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
```
which ignored any GPU entirely — no benefit from the server's NVIDIA card.

Fixed: device and precision are now configurable via `config.py` /
`.env`:
- `WHISPER_DEVICE` (default `"auto"` — uses CUDA if available, otherwise CPU)
- `WHISPER_COMPUTE_TYPE` (default `"int8"`; try `"float16"` on a GPU machine for a
  real speed/quality improvement over the CPU-safe default)

Both changes keep their old behavior by default, so nothing breaks on machines
without a GPU (e.g. the original Windows dev setup).

## Deployment steps

**1. Install Ubuntu** (22.04 or 24.04 LTS). Prefer **Ubuntu Server** (no desktop GUI)
for a dedicated always-on box — leaner, and managed headless over SSH.

**2. Install the NVIDIA driver and verify the GPU:**
```bash
sudo ubuntu-drivers autoinstall
sudo reboot
nvidia-smi   # should list the GPU
```

**3. Install system packages:**
```bash
sudo apt update
sudo apt install -y git curl build-essential libopus0
```
`libopus0` is what makes the Opus fix above actually resolve.

**4. Install `uv`:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**5. Install Ollama** (auto-detects the NVIDIA GPU, no config needed) and pull the
models this project uses:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral
ollama pull nomic-embed-text
```

**6. Get the code:**
```bash
git clone <your-repo-url> dm_scribe
cd dm_scribe
```

**7. Configure `.env`:**
```bash
cp .env.example .env
```
Fill in `DISCORD_TOKEN` (the same bot application/token used elsewhere), and set:
```
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
```
to actually use the GPU for transcription.

> ⚠️ **Only run one instance of a given `DISCORD_TOKEN` at a time.** Stop the bot on
> any other machine (e.g. the original Windows dev setup) before starting it here —
> two processes on the same token will fight over the same Discord gateway
> connection and cause duplicate/conflicting command registrations.

**8. Install dependencies and do a manual test run:**
```bash
uv sync
uv run python run.py
```
Watch the logs for `Loaded Opus library: ...` (confirms the Linux fix worked), then
do a real `/join` → `/inscribe` → `/stop` test in Discord.

**9. Run it as a systemd service** so it survives reboots and crashes:
```ini
# /etc/systemd/system/dm-scribe.service
[Unit]
Description=DM Scribe Discord Bot
After=network-online.target

[Service]
WorkingDirectory=/home/youruser/dm_scribe
ExecStart=/home/youruser/.local/bin/uv run python run.py
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now dm-scribe
```

## Remote access to Chroma + Ollama (lore ingestion + Q&A from another machine)

By default Chroma runs embedded (just a local directory, no network listener) and
Ollama only listens on `localhost`. That's fine for the bot itself (everything runs
on the one server), but `src/ingest_lore.py` and `src/ask.py` are meant to be run
from wherever's convenient — e.g. your laptop — so both need to be reachable over
the network.

### 1. Make Ollama reachable remotely

By default Ollama only binds to `127.0.0.1`. To accept connections from elsewhere,
set `OLLAMA_HOST=0.0.0.0` for the Ollama service itself (this is Ollama's own env
var for its bind address, unrelated to this project's `OLLAMA_HOST` config value,
which is the *client-side* URL other processes use to reach it):
```bash
sudo systemctl edit ollama
```
Add:
```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```
```bash
sudo systemctl restart ollama
```

### 2. Run Chroma as its own server

Instead of the bot's embedded Chroma client, run Chroma as a standalone service so
it can be reached from elsewhere too:
```bash
uv run chroma run --path ./vector_store --host 0.0.0.0 --port 8000
```
Or as its own systemd unit (recommended for anything long-running):
```ini
# /etc/systemd/system/chroma.service
[Unit]
Description=Chroma vector store
After=network-online.target

[Service]
WorkingDirectory=/home/youruser/dm_scribe
ExecStart=/home/youruser/.local/bin/uv run chroma run --path ./vector_store --host 0.0.0.0 --port 8000
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now chroma
```

Then point the bot itself at this server instead of its embedded store, so there's
one Chroma, not two out-of-sync copies — add to the server's `.env`:
```
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

### 3. Do NOT expose either port to the open internet

Neither Ollama nor Chroma have meaningful built-in authentication in the versions
this project uses. Exposing `11434` or `8000` directly to the internet means anyone
who finds them can run arbitrary prompts against your GPU (resource abuse) or read/
write your session data. Restrict access instead:

- **Tailscale (recommended)** — install on both the server and your laptop, then use
  the server's Tailscale IP/hostname for `OLLAMA_HOST`/`CHROMA_HOST` on the laptop.
  Nothing is exposed publicly; only devices in your Tailscale network can reach it.
- **SSH tunnel** (lighter-weight, no extra install) — from your laptop:
  ```bash
  ssh -L 11434:localhost:11434 -L 8000:localhost:8000 youruser@server
  ```
  then use `OLLAMA_HOST=http://localhost:11434` and `CHROMA_HOST=localhost` on the
  laptop — traffic is tunneled through the SSH connection.
- If you must use a firewall rule instead, restrict it to your laptop's specific IP,
  never `0.0.0.0/0`.

### 4. Ingest lore and ask questions from your laptop

With `.env` on your laptop pointed at the server's `OLLAMA_HOST`/`CHROMA_HOST` (via
whichever of the above you chose):
```bash
python src/ingest_lore.py --guild-id 123456789012345678 homebrew_lore.md campaign_notes.md
python src/ask.py --guild-id 123456789012345678 "Who leads the dragon cult?"
```
`ask.py` retrieves relevant session summaries and lore chunks, then asks the
summarization LLM to synthesize an answer from them — unlike Discord's `/recall`
command, which only surfaces the raw matches.

## Validating it worked

- Bot logs should show `Loaded Opus library: ...` on startup (not the "Opus library
  is not loaded" warning).
- `nvidia-smi` should show GPU utilization during `/stop` (Ollama inference, and
  Whisper transcription if `WHISPER_DEVICE=cuda`).
- `session_metrics.jsonl` (see `CLAUDE.md`) logs real transcription/summarization
  timing per session — compare against numbers from the original CPU-only Windows
  setup to see whether the GPU move actually helped, rather than assuming it did.
- If set up for remote access, `python src/ask.py --guild-id <id> "test"` from your
  laptop should return an answer (or the "no relevant sessions or lore found"
  message if nothing's been ingested yet) rather than a connection error.

## Related docs

- `README.md` — general setup, Ollama basics, command reference.
- `CLAUDE.md` — architecture overview, including `session_metrics.jsonl` and the
  `WHISPER_DEVICE`/`WHISPER_COMPUTE_TYPE`/`OLLAMA_MODEL` config knobs referenced above.
- `dm_scribe_hosting.md` — an earlier, more speculative hosting doc (Railway/Heroku/
  Docker-based cloud hosting, none of it implemented yet). It happens to mention an
  `OLLAMA_HOST` env var too, but as a Railway-specific variable name, not this
  project's `config.OLLAMA_HOST` added here — don't conflate the two. This file
  supersedes it for the "dedicated server you control" scenario; that one may be
  worth revisiting or removing if a managed-cloud-platform path becomes relevant
  later.
