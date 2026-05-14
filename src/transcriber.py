"""
Handles speech-to-text transcription.
"""

from faster_whisper import WhisperModel
from config import WHISPER_MODEL
from utils import save_transcript_for_training, logging
import requests
from datetime import datetime
import os


class Transcriber:
    def __init__(self):
        self.model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    def transcribe_audio(self, audio_file_path, session_id=None, channel_name=None):
        """
        Transcribe audio file to text using faster-whisper.

        Args:
            audio_file_path: Path to the audio file
            session_id: Optional session identifier for training data
            channel_name: Optional channel name for context

        Returns:
            str: Transcribed text
        """
        try:
            segments, info = self.model.transcribe(audio_file_path, beam_size=5)
            text = " ".join([segment.text for segment in segments])

            # Save for training if session info provided
            if session_id and text.strip():
                save_transcript_for_training(text, session_id, channel_name or "unknown")

            return text
        except Exception as e:
            logging.error(f"Transcription error: {e}")
            return ""

    def process_audio_chunk(self, audio_chunk, session_id=None, channel_name=None):
        """Process a chunk of audio data."""
        return self.transcribe_audio(audio_chunk, session_id, channel_name)

    def enhance_transcription(self, transcription, character_map):
        """Enhance transcription by replacing speaker names with character names."""
        # This is a simple placeholder; in reality, you'd need speaker diarization
        # For now, assume the transcription is dialogue and replace known names
        enhanced = transcription
        for discord_handle, info in character_map.items():
            character_name = info.get("name", discord_handle)
            # Replace mentions of discord_handle with character name
            enhanced = enhanced.replace(discord_handle, character_name)
        return enhanced

    def summarize_with_llm(self, transcription, character_map):
        """Use local Mistral 7B via Ollama to summarize the transcription."""
        try:
            char_info = "\n".join(
                [
                    (f"{handle}: {info['name']} - "
                        "Class: {info.get('class', 'Unknown')}, "
                        "Species: {info.get('species', 'Unknown')}, "
                        "Gender: {info.get('gender', 'Unknown')}")
                    for handle, info in character_map.items()
                ]
            )
            prompt = f"""
            Summarize the following D&D session transcription. Focus on:
            - Key events and plot points
            - Lore and world-building details
            - Loot and items acquired
            - Character actions and decisions

            Character details:
            {char_info}

            Transcription: {transcription}

            Provide a brief summary, notes on lore/loot, and any memorable quotes.
            """
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "mistral", "prompt": prompt, "stream": False},
            )
            if response.status_code == 200:
                return response.json()["response"]
            else:
                return f"Error: {response.status_code} - {response.text}"
        except Exception as e:
            logging.error(f"LLM summary error: {e}")
            return "Summary unavailable. Ensure Ollama is running with 'ollama serve'."

    def save_obsidian_note(self, summary, character_map, session_name=None):
        """
        Save the session summary as an Obsidian markdown file.

        Args:
            summary: LLM-generated summary
            character_map: Dict of character assignments
            session_name: Optional custom session name

        Returns:
            str: Path to the saved file
        """
        try:
            # Create notes directory if it doesn't exist
            if not os.path.exists("obsidian_notes"):
                os.makedirs("obsidian_notes")

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"obsidian_notes/D&D_Session_{timestamp}.md"

            # Extract character list from character_map
            characters = "\n".join(
                [
                    (f"- **{info['name']}** "
                     f"({info.get('class', 'Unknown')} {info.get('species', 'Unknown')})")
                    for info in character_map.values()
                ]
            )

            # Create Obsidian markdown with frontmatter
            content = f"""---
created: {datetime.now().isoformat()}
type: dnd-session
session_name: {session_name or f"Session {timestamp}"}
---

# D&D Session Notes

**Date**: {datetime.now().strftime("%B %d, %Y")}
**Time**: {datetime.now().strftime("%I:%M %p")}

## Players & Characters

{characters if characters else "No characters assigned"}

## Session Summary

{summary}

---
*Generated by DM Scribe Bot*
"""

            # Write to file
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)

            return filename
        except Exception as e:
            logging.error(f"Error saving Obsidian note: {e}")
            return None
