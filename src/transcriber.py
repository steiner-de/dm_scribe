"""
Handles speech-to-text transcription.
"""

from faster_whisper import WhisperModel
from config import OLLAMA_MODEL, WHISPER_MODEL
from utils import logging
import requests
from datetime import datetime
import os


class Transcriber:
    def __init__(self):
        self.model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    def transcribe_speakers(self, user_files, character_map):
        """
        Transcribe each speaker's isolated audio track and merge the
        results into one chronological transcript labeled by character
        name. Speaker attribution comes from Discord's per-user audio
        streams (see voice_handler.VoiceHandler), not diarization.

        Args:
            user_files: {discord_user_id: path_to_wav}
            character_map: character assignment map keyed by discord user id

        Returns:
            str: merged transcript, one line per speech segment, sorted by
                 time and labeled with the speaker's character name
        """
        entries = []
        for user_id, path in user_files.items():
            label = self._label_for_user(user_id, character_map)
            try:
                segments, _ = self.model.transcribe(path, beam_size=5)
            except Exception as e:
                logging.error(f"Transcription error for {path}: {e}")
                continue
            for segment in segments:
                text = segment.text.strip()
                if text:
                    entries.append((segment.start, label, text))

        entries.sort(key=lambda entry: entry[0])
        return "\n".join(
            f"[{self._format_timestamp(start)}] {label}: {text}"
            for start, label, text in entries
        )

    @staticmethod
    def _label_for_user(user_id, character_map):
        """Resolve a Discord user ID to their assigned character name."""
        info = character_map.get(str(user_id))
        if info:
            return info.get("name", str(user_id))
        return f"User {user_id}"

    @staticmethod
    def _format_timestamp(seconds):
        minutes, secs = divmod(int(seconds), 60)
        return f"{minutes:02d}:{secs:02d}"

    def summarize_with_llm(self, transcription, character_map):
        """Use a local LLM via Ollama to summarize the transcription."""
        try:
            char_info = "\n".join(
                [
                    (f"{handle}: {info['name']} - "
                        f"Class: {info.get('class', 'Unknown')}, "
                        f"Species: {info.get('species', 'Unknown')}, "
                        f"Gender: {info.get('gender', 'Unknown')}")
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
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
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
