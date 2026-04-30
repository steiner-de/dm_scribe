"""
Handles speech-to-text transcription.
"""

import speech_recognition as sr
import stt  # Coqui STT
from config import TRANSCRIPTION_SERVICE, WHISPER_MODEL
from utils import save_transcript_for_training, logging

class Transcriber:
    def __init__(self):
        self.model = None
        if TRANSCRIPTION_SERVICE == 'coqui':
            # Initialize Coqui STT model
            # You'll need to download and specify the model path
            model_path = "path/to/coqui/model"  # Update this
            self.model = stt.Model(model_path)
        else:
            self.recognizer = sr.Recognizer()

    def transcribe_audio(self, audio_data, session_id=None, channel_name=None):
        """
        Transcribe audio data to text.

        Args:
            audio_data: Raw audio bytes or AudioData object
            session_id: Optional session identifier for training data
            channel_name: Optional channel name for context

        Returns:
            str: Transcribed text
        """
        try:
            if TRANSCRIPTION_SERVICE == 'coqui':
                # Coqui STT transcription
                text = self.model.stt(audio_data)
            elif TRANSCRIPTION_SERVICE == 'google':
                # Use Google Speech Recognition
                audio = sr.AudioData(audio_data, 16000, 2)
                text = self.recognizer.recognize_google(audio)
            else:
                text = "Transcription service not configured"

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