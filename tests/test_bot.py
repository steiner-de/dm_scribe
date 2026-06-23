"""
Basic tests for the Discord bot.
"""

import unittest
import sys
import os
import config

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestBot(unittest.TestCase):
    def test_config_loaded(self):
        """Test that configuration is loaded."""
        self.assertTrue(hasattr(config, "DISCORD_TOKEN"))
        self.assertTrue(hasattr(config, "COMMAND_PREFIX"))
        self.assertTrue(hasattr(config, "BOT_ACTIVITY"))

    # def test_imports(self):
    #     """Test that modules can be imported."""
    #     try:
    #         from bot import TranscriberBot
    #         from voice_handler import VoiceHandler
    #         from transcriber import Transcriber
    #         from utils import setup_logging
    #     except ImportError as e:
    #         self.fail(f"Import failed: {e}")


if __name__ == "__main__":
    unittest.main()
