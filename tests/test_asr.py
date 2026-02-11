import sys
import os
import time
import numpy as np

# Add root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_assistant.asr import ASR
from rich.console import Console

console = Console()

def create_sine_wave(duration_sec=1.0, freq=440, rate=16000):
    """Generate a sine wave audio (beep) for testing (ASR likely won't recognize it as text)"""
    t = np.linspace(0, duration_sec, int(rate * duration_sec), False)
    # Generate int16 range
    audio = np.sin(freq * t * 2 * np.pi) * 32767
    return audio.astype(np.int16).tobytes()

def main():
    console.print("[bold green]ASR Module Test (Sherpa-ONNX)[/bold green]")
    console.print(f"Python: {sys.executable}")
    console.print(f"Prefix: {sys.prefix}")
    
    # 1. Init
    console.print("Initializing ASR (loading model)... This may take a while first time.")
    start = time.time()
    try:
        # ASR init no longer takes model_size, it uses hardcoded path for Phase 2
        asr = ASR() 
        console.print(f"Model loaded in {time.time() - start:.2f}s")
    except Exception as e:
        console.print(f"[bold red]Failed to load Sherpa-ONNX model: {e}[/bold red]")
        console.print("Please ensure sherpa-onnx is installed and model is downloaded (run download_sherpa_model.py).")
        return
    
    # 2. Test with silence/noise (should output empty or garbage)
    console.print("\nTesting with 1s silence...")
    silence = b'\x00' * 16000 * 2 # 1 sec, 16kHz, 16bit
    text = asr.transcribe(silence)
    console.print(f"Result (Silence): '{text}'")
    
    # 3. Mic Test (Interactive)
    console.print("\n[bold yellow]Interactive Test:[/bold yellow]")
    console.print("We will record 3 seconds of audio from your mic to test recognition.")
    console.print("Press ENTER to start recording...")
    input()
    
    try:
        import pyaudio
        chunk = 1024
        rate = 16000
        p = pyaudio.PyAudio()
        
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True, frames_per_buffer=chunk)
        
        console.print("[red]Recording 3 seconds... Speak now![/red]")
        frames = []
        for i in range(0, int(rate / chunk * 3)):
            data = stream.read(chunk)
            frames.append(data)
            
        console.print("[green]Recording stopped.[/green]")
        stream.stop_stream()
        stream.close()
        p.terminate()
        
        audio_data = b''.join(frames)
        
        console.print("Transcribing recorded audio...")
        start = time.time()
        text = asr.transcribe(audio_data)
        console.print(f"Transcribed in {time.time() - start:.2f}s")
        console.print(f"\n[bold white on blue] Recognized Text: [/bold white on blue] {text}")
        
    except ImportError:
         console.print("[red]PyAudio not installed, skipping mic test.[/red]")
    except Exception as e:
         console.print(f"[red]Mic test failed: {e}[/red]")

if __name__ == "__main__":
    main()
