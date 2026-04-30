"""
Utility functions for the bot.
"""

import logging
from datetime import datetime
import json
import os
from config import DEFAULT_TEXT_CHANNEL

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log'),
            logging.StreamHandler()
        ]
    )

def format_timestamp():
    """Get current timestamp in readable format."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def sanitize_text(text):
    """Clean up transcribed text."""
    # Remove extra whitespace, etc.
    return ' '.join(text.split())

def get_user_display_name(user):
    """Get the display name for a Discord user."""
    return user.display_name if hasattr(user, 'display_name') else str(user)

def save_transcript_for_training(transcript, session_id, channel_name):
    """Save transcript data for LLM training."""
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'training_data')
    os.makedirs(data_dir, exist_ok=True)

    data = {
        'session_id': session_id,
        'channel': channel_name,
        'timestamp': format_timestamp(),
        'transcript': sanitize_text(transcript),
        'source': 'discord_voice_call'
    }

    filename = f"transcript_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(data_dir, filename)

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    logging.info(f"Saved transcript for training: {filepath}")

def export_training_data(output_path=None):
    """Export all collected training data to a single file for LLM repo."""
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'training_data')
    if not os.path.exists(data_dir):
        logging.warning("No training data directory found")
        return

    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), '..', 'exported_training_data.jsonl')

    with open(output_path, 'w') as outfile:
        for filename in os.listdir(data_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(data_dir, filename)
                with open(filepath, 'r') as infile:
                    data = json.load(infile)
                    # Convert to JSON Lines format for training
                    json.dump(data, outfile)
                    outfile.write('\n')

    logging.info(f"Exported training data to: {output_path}")
    return output_path