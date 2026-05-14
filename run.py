#!/usr/bin/env python3
"""
Entry point for the Discord Voice Call Transcriber Bot.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from bot import main

if __name__ == "__main__":
    main()
