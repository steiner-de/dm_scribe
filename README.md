# Discord Voice Call Transcriber Bot

## Project Overview
This Discord bot is designed to join voice channels in Discord servers and transcribe audio from voice calls, particularly useful for tabletop gaming sessions like Dungeons & Dragons (D&D) or other role-playing games. The bot will capture audio from participants, convert speech to text, and potentially log or display transcriptions in real-time.

## Key Features
- Join voice channels on command
- Capture audio from all participants
- Real-time speech-to-text transcription
- Output transcriptions to text channels or logs
- Configurable for different servers/channels
- Handle multiple speakers and noise reduction (optional)

## Requirements
- Python 3.11+
- Discord.py library
- Speech recognition library (e.g., SpeechRecognition, or cloud services like Google Speech API, OpenAI Whisper)
- Audio processing libraries (e.g., PyAudio, pydub)
- Discord Bot Token (from Discord Developer Portal)

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
1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `.env` file with your Discord bot token
4. Run the bot: `python run.py`

## Configuration
- Set bot token in config.py or environment variables
- Configure transcription service API keys
- Set default text channel for outputs

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