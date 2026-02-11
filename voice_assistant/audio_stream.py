import collections
from pathlib import Path
from typing import Optional, List

import pyaudio
import yaml

# Redesign for simpler blocking usage in loop:
class MicrophoneStream:
    def __init__(self, rate=16000, chunk=512):
        self.rate = rate
        self.chunk = chunk
        self.pa = pyaudio.PyAudio()
        self.stream = None
        pre_roll_sec = self._load_pre_roll_sec()
        self.queue = collections.deque(maxlen=int(rate / chunk * pre_roll_sec))

    def _load_pre_roll_sec(self) -> float:
        config_path = Path(__file__).resolve().parents[1] / "config.yaml"
        if not config_path.exists():
            return 1.0
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return 1.0
        audio = data.get("audio", {})
        if not isinstance(audio, dict):
            return 1.0
        value = audio.get("pre_roll_sec", 1.0)
        try:
            sec = float(value)
        except Exception:
            return 1.0
        if sec <= 0:
            return 1.0
        return sec

    def __enter__(self):
        self.stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.pa.terminate()

    def read(self) -> bytes:
        data = self.stream.read(self.chunk, exception_on_overflow=False)
        self.queue.append(data)
        return data

    def get_pre_roll(self) -> bytes:
        return b''.join(self.queue)
