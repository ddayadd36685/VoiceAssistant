import uvicorn
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("Starting Voice Assistant Server on http://127.0.0.1:8000")
    uvicorn.run("voice_assistant.server:app", host="127.0.0.1", port=8000, reload=False)
