"""
Utility functions for the bot.
"""

import logging
from datetime import datetime
import json
import os
import wave


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
    )


def format_timestamp():
    """Get current timestamp in readable format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize_text(text):
    """Clean up transcribed text."""
    # Remove extra whitespace, etc.
    return " ".join(text.split())


def get_user_display_name(user):
    """Get the display name for a Discord user."""
    return user.display_name if hasattr(user, "display_name") else str(user)


SUMMARIZATION_INSTRUCTION = (
    "Summarize the following D&D session transcript. Focus on key events and plot "
    "points, lore and world-building details, loot and items acquired, and character "
    "actions and decisions."
)


def save_transcript_for_training(transcript, summary, session_id, channel_name):
    """Save a transcript + its summary as a training example for fine-tuning.

    Storing both (rather than just the transcript) is what lets
    export_training_data() build instruction/response pairs later.
    """
    data_dir = os.path.join(os.path.dirname(__file__), "..", "training_data")
    os.makedirs(data_dir, exist_ok=True)

    data = {
        "session_id": session_id,
        "channel": channel_name,
        "timestamp": format_timestamp(),
        "transcript": sanitize_text(transcript),
        "summary": sanitize_text(summary),
        "source": "discord_voice_call",
    }

    filename = f"transcript_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(data_dir, filename)

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    logging.info(f"Saved transcript for training: {filepath}")


def export_training_data(output_path=None):
    """
    Export collected session transcripts as instruction/response pairs
    (see DND_LLM_GUIDE.md) ready for train_llm.py.

    Records saved before summary capture was added (no "summary" field) are
    skipped, since they can't form a valid instruction/response pair.
    """
    data_dir = os.path.join(os.path.dirname(__file__), "..", "training_data")
    if not os.path.exists(data_dir):
        logging.warning("No training data directory found")
        return

    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "..", "exported_training_data.jsonl")

    written = 0
    skipped = 0
    with open(output_path, "w") as outfile:
        for filename in sorted(os.listdir(data_dir)):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r") as infile:
                data = json.load(infile)

            summary = data.get("summary")
            transcript = data.get("transcript")
            if not summary or not transcript:
                skipped += 1
                continue

            example = {
                "instruction": f"{SUMMARIZATION_INSTRUCTION}\n\nTranscript: {transcript}",
                "response": summary,
            }
            json.dump(example, outfile)
            outfile.write("\n")
            written += 1

    logging.info(
        f"Exported {written} training example(s) to: {output_path} "
        f"({skipped} skipped: missing summary)"
    )
    return output_path


SESSION_METRICS_FILE = os.path.join(os.path.dirname(__file__), "..", "session_metrics.jsonl")


def get_wav_duration_seconds(path):
    """Return a WAV file's duration in seconds, or 0.0 if it can't be read."""
    try:
        with wave.open(path, "rb") as f:
            return f.getnframes() / float(f.getframerate())
    except (wave.Error, OSError, EOFError) as e:
        logging.error(f"Failed to read WAV duration for {path}: {e}")
        return 0.0


def log_session_metrics(**metrics):
    """
    Append one session's timing/size metrics as a JSON line, for measuring
    real transcription/summarization cost during playtesting (see
    bot.process_recording). Never raises -- a failed metrics write
    shouldn't break session processing.
    """
    record = {"timestamp": format_timestamp(), **metrics}
    try:
        with open(SESSION_METRICS_FILE, "a", encoding="utf-8") as f:
            json.dump(record, f)
            f.write("\n")
    except IOError as e:
        logging.error(f"Failed to log session metrics: {e}")
