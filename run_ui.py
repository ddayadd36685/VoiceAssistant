import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from voice_assistant.ui.app import main

if __name__ == "__main__":
    print("Starting Voice Assistant UI...")
    raise SystemExit(main())
