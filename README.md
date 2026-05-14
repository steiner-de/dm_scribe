# Discord Voice Call Transcriber Bot

## Project Overview
This Discord bot is designed to join voice channels in Discord servers and transcribe audio from voice calls, particularly useful for tabletop gaming sessions like Dungeons & Dragons (D&D) or other role-playing games. The bot will capture audio from participants, convert speech to text, and potentially log or display transcriptions in real-time.

## Key Features
- Join/leave voice channels on command
- Record audio from voice calls
- Transcribe recordings using faster-whisper
- Enhance transcriptions with character names
- Summarize sessions with local Mistral LLM (lore, loot, events)
- Assign character details for better context
- Persistent character mappings across sessions

## Requirements
- Python 3.11+
- Ollama (for local LLM): Download from https://ollama.ai
- Discord Bot Token (from Discord Developer Portal)

### Dependencies
Install Python packages:
```bash
pip install -r requirements.txt
```

### Ollama Setup
1. Install Ollama from https://ollama.ai
2. Pull the Mistral model:
   ```bash
   ollama pull mistral
   ```
3. Start the Ollama server:
   ```bash
   ollama serve
   ```
   (Keep this running in the background for the bot to use the LLM.)

## Project Structure
```
discord_video_call_transcriber/
├── src/
│   ├── bot.py              # Main bot logic
│   ├── voice_handler.py    # Voice connection and audio capture
│   ├── transcriber.py      # Speech-to-text processing
│   ├── config.py           # Configuration and secrets
│   └── utils.py            # Utility functions
├── tests/
│   └── test_bot.py
├── requirements.txt
├── .gitignore
├── README.md
└── run.py                  # Entry point
```

## Implementation Steps

### 1. Setup Discord Bot
- Create a Discord application at https://discord.com/developers/applications
- Generate a bot token
- Invite the bot to your server with appropriate permissions (voice, text)

### 2. Basic Bot Framework
- Install discord.py
- Create basic bot that responds to commands
- Implement slash commands or prefix commands

### 3. Voice Channel Joining
- Add command to join voice channel (e.g., /join)
- Handle voice client connection
- Detect when users speak

### 4. Audio Capture
- Set up audio stream from voice channel
- Handle multiple audio sources
- Buffer audio data

### 5. Speech Recognition
- Choose transcription service (local vs cloud)
- Process audio chunks
- Convert to text

### 6. Output and Logging
- Send transcriptions to text channel
- Log to file or database
- Handle speaker identification (optional)

### 7. Error Handling and Optimization
- Handle disconnections
- Noise filtering
- Rate limiting and performance

### 8. Testing and Deployment
- Test in a private server
- Add logging and monitoring
- Deploy to a server or cloud service

## Getting Started

### Prerequisites
- Python 3.11+
- Discord Bot Token (from https://discord.com/developers/applications)
- Ollama (for local LLM)

### Installation

#### Step 1: Clone and Install Python Packages
```bash
git clone <repo-url>
cd dm_scribe
pip install -r requirements.txt
```

#### Step 2: Setup Discord Bot
1. Go to https://discord.com/developers/applications
2. Create a new application
3. Go to "Bot" and create a bot
4. Copy the bot token
5. Under "OAuth2" > "URL Generator", select `bot` and `Send Messages`, `Connect`, `Speak`
6. Use the generated URL to invite the bot to your server

#### Step 3: Configure Environment
```bash
cp .env.example .env
```
Edit `.env` and add your Discord bot token:
```
DISCORD_TOKEN=your_bot_token_here
```

#### Step 4: Install and Setup Ollama

**On Windows:**
1. Download Ollama from https://ollama.ai (Windows installer)
2. Run the installer and complete setup
3. Open PowerShell and pull the Mistral model:
   ```powershell
   ollama pull mistral
   ```
4. Start the Ollama server (in a separate PowerShell window or as a background service):
   ```powershell
   ollama serve
   ```
   - **Note**: The server will run on `http://localhost:11434` and must be running when the bot needs to generate summaries.
   - **Tip**: To run Ollama in the background without a dedicated window, you can create a scheduled task or use Windows Task Scheduler to auto-start it.

**On macOS:**
1. Download Ollama from https://ollama.ai (Mac installer)
2. Run the installer
3. Pull the Mistral model:
   ```bash
   ollama pull mistral
   ```
4. Start the server:
   ```bash
   ollama serve
   ```

**On Linux:**
1. Install via script:
   ```bash
   curl https://ollama.ai/install.sh | sh
   ```
2. Pull Mistral:
   ```bash
   ollama pull mistral
   ```
3. Start the server:
   ```bash
   ollama serve
   ```

#### Step 5: Run the Bot
In a separate PowerShell/Terminal window (keep Ollama serving in another):
```bash
python run.py
```

The bot should log in. In Discord, test with `!help` to see available commands.

### Running the Bot

**On Windows (Simple - Recommended):**
1. Open PowerShell and run:
   ```powershell
   python run.py
   ```
2. The bot will start. Ollama will be started automatically when you use `!stop` for the first time.

**On Windows (Manual Ollama):**
If you prefer to start Ollama manually:
1. Open PowerShell window #1 and run:
   ```powershell
   ollama serve
   ```
2. Open PowerShell window #2 and run:
   ```powershell
   python run.py
   ```

**On Windows (Background Task - Optional):**
To run Ollama automatically on startup:
1. Open Task Scheduler (search "Task Scheduler" in Start menu)
2. Create Basic Task > Name it "Ollama Server"
3. Set trigger to "At startup"
4. Set action to "Start a program" > Program: `C:\Users\<YourUsername>\AppData\Local\Programs\Ollama\ollama.exe` > Arguments: `serve`
5. Click OK. Ollama will now start automatically.

**Ollama Server Lifecycle:**
- Ollama **must be running** whenever you use the `!stop` command (which generates LLM summaries).
- The bot will **automatically start Ollama** if it detects it's not running (when you use `!stop`).
- You can still manually start it with `ollama serve` or via Task Scheduler for continuous operation.
- Turning it off manually saves system resources but the bot will restart it as needed.

## Bot Commands

Once the bot is running and connected to your Discord server, use the following commands:

| Command | Description | Example |
|---------|-------------|---------|
| `!name_me <name>` | Set the bot's nickname in the server | `!name_me Scribe` |
| `!join` | Bot joins your current voice channel | `!join` |
| `!leave` | Bot leaves the voice channel | `!leave` |
| `!scribe` | Start recording audio from the voice channel | `!scribe` |
| `!stop` | Stop recording, transcribe, generate LLM summary. Creates Obsidian note and posts to notes channel. | `!stop` |
| `!assign_character <@user> <character> [class] [species] [gender]` | Assign a character name to a player for transcription enhancement | `!assign_character @John Fighter Dwarf Male` |
| `!remove_character <@user>` | Remove a player's character assignment | `!remove_character @John` |
| `!list_characters` | List all assigned player-to-character mappings | `!list_characters` |
| `!set_notes_channel <#channel>` | Set which channel session summaries are posted to (admin only) | `!set_notes_channel #session-notes` |
| `!get_notes_channel` | Show the current notes channel for this server | `!get_notes_channel` |
| `!help` | Show all available commands | `!help` |

### Typical D&D Session Workflow
1. All players join the Discord voice channel
2. Run `!join` to have the bot join the channel
3. Run `!scribe` to start recording
4. Play your D&D session normally
5. Run `!stop` when done—the bot will transcribe and summarize with Mistral LLM
6. Review the transcription and summary posted to Discord

## Configuration
- Set bot token in config.py or environment variables
- Configure transcription service API keys
- Set default text channel for outputs

## Development & Linting

### Setup Development Environment
Install development dependencies:

**On macOS/Linux:**
```bash
pip install -r requirements-dev.txt
```

**On Windows (PowerShell):**
```powershell
pip install -r requirements-dev.txt
```

### Running Linters

**Format code with Black:**

Bash/Zsh:
```bash
black src/ tests/ run.py
```

PowerShell:
```powershell
black src/, tests/, run.py
```

**Check code style with Flake8:**

Bash/Zsh:
```bash
flake8 src/ tests/ run.py
```

PowerShell:
```powershell
flake8 src/ tests/ run.py
```

**Check with Ruff (faster alternative):**

Bash/Zsh:
```bash
ruff check src/ tests/ run.py
```

PowerShell:
```powershell
ruff check src/ tests/ run.py
```

### Linting Configuration
Linting rules are configured in `pyproject.toml`:
- **Black**: Line length 100, Python 3.11+ target
- **Flake8**: Line length 100, ignores E203 and W503
- **Ruff**: Similar configuration for fast linting

### Pre-commit Hook (Optional)
To automatically lint on commit, install pre-commit:

Bash/Zsh:
```bash
pip install pre-commit
pre-commit install
```

PowerShell:
```powershell
pip install pre-commit
pre-commit install
```
```

## Notes
- Be mindful of Discord's Terms of Service regarding audio recording
- Ensure proper permissions and user consent for voice recording
- Consider privacy implications of transcribing conversations

## Next Steps
Follow the implementation steps above to build the bot incrementally. Start with basic bot setup and voice joining, then add transcription features.

## LLM Integration and Continuous Learning
This bot is designed to collect transcription data for improving your custom D&D LLM:

- **Data Collection**: Transcripts are automatically saved during voice calls for training.
- **Export for Training**: Use the `/export_data` command (admin only) to export collected data to `exported_training_data.jsonl`.
- **LLM Updates**: Transfer the exported file to your separate `dnd-homebrew-llm` repo for fine-tuning.
- **Integration**: Connect the trained LLM via API for summarization and lore generation features.

See `DND_LLM_GUIDE.md` for LLM training details.

## Character Mapping for D&D Sessions
In D&D games, each player voices a specific character. To attribute transcriptions correctly, you can map Discord users to their character names.

### Implementation Approach
1. **Mapping Storage**: Create a `character_mappings.json` file with user ID to character name mappings:
   ```json
   {
     "character_mappings": {
       "123456789012345678": "Elric",
       "987654321098765432": "Thrain"
     }
   }
   ```

2. **Setting Mappings**: Add a bot command like `/set_character <name>` for users to register their character.

3. **Speaker Identification**: 
   - **Challenge**: Discord voice audio is mixed; identifying who is speaking requires speaker diarization.
   - **Basic Solution**: Assume sequential speaking or use voice activity detection per user (if Discord provides it).
   - **Advanced Solution**: Integrate a speaker diarization library like `pyannote.audio` to separate voices in the audio stream.

4. **Transcription Labeling**: When transcribing, prepend the character name: "[Elric]: I cast fireball..."

5. **Fallback**: If speaker can't be identified, use generic labels or let the LLM infer from context.

### Steps to Implement
- Add `pyannote.audio` to requirements for diarization.
- Modify `voice_handler.py` to process audio with speaker separation.
- Update `transcriber.py` to include speaker labels in output.
- Save labeled transcripts for LLM training to improve character attribution.

This ensures transcripts reflect the role-play, making summaries and lore generation more accurate.