import math
import struct
import time
from pathlib import Path
from typing import Optional

import yaml

from .logger import get_logger

class VadRecorder:
    def __init__(self, silence_limit_sec=1.5, rate=16000, chunk=512):
        self.silence_limit_sec = silence_limit_sec
        self.wakeup_silence_limit_sec = 2.5
        self.wakeup_silence_ramp_sec = 1.0
        self.rate = rate
        self.chunk = chunk
        self.silence_threshold = 500
        self.max_recording_sec = 10.0
        self.chunks_per_sec = rate / chunk
        self.logger = get_logger(__name__)
        self._apply_config()

    def _current_silence_limit_sec(self, elapsed_sec: float) -> float:
        start = float(self.wakeup_silence_limit_sec)
        end = float(self.silence_limit_sec)
        ramp = float(self.wakeup_silence_ramp_sec)
        if ramp <= 0:
            return end
        if elapsed_sec <= 0:
            return max(end, start)
        if elapsed_sec >= ramp:
            return end
        t = elapsed_sec / ramp
        return (start * (1.0 - t)) + (end * t)

    def _apply_config(self):
        config_path = Path(__file__).resolve().parents[1] / "config.yaml"
        if not config_path.exists():
            return
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return
        vad = data.get("vad", {})
        if not isinstance(vad, dict):
            return
        silence_threshold = vad.get("silence_threshold", self.silence_threshold)
        max_recording_sec = vad.get("max_recording_sec", self.max_recording_sec)
        wakeup_silence_limit_sec = vad.get("wakeup_silence_limit_sec", self.wakeup_silence_limit_sec)
        wakeup_silence_ramp_sec = vad.get("wakeup_silence_ramp_sec", self.wakeup_silence_ramp_sec)
        try:
            self.silence_threshold = float(silence_threshold)
        except Exception:
            pass
        try:
            self.max_recording_sec = float(max_recording_sec)
        except Exception:
            pass
        try:
            self.wakeup_silence_limit_sec = float(wakeup_silence_limit_sec)
        except Exception:
            pass
        try:
            self.wakeup_silence_ramp_sec = float(wakeup_silence_ramp_sec)
        except Exception:
            pass

    def capture(self, stream, pre_roll: bytes = b'') -> bytes:
        """
        Capture audio from stream until silence is detected.
        """
        start_ts = time.monotonic()
        frames = [pre_roll]
        silence_chunks = 0
        max_recording_chunks = int(self.max_recording_sec * self.chunks_per_sec)
        
        self.logger.info("Started recording...")
        
        while len(frames) < max_recording_chunks:
            data = stream.read()
            frames.append(data)
            elapsed_sec = time.monotonic() - start_ts
            silence_limit_sec = self._current_silence_limit_sec(elapsed_sec)
            max_silence_chunks = max(1, int(silence_limit_sec * self.chunks_per_sec))
            
            if self._is_silent(data):
                silence_chunks += 1
            else:
                silence_chunks = 0
            
            if silence_chunks > max_silence_chunks:
                self.logger.info("Silence detected, stopping recording.")
                break
        
        return b''.join(frames)

    def _is_silent(self, chunk: bytes) -> bool:
        if not chunk:
            return True
        count = len(chunk) // 2
        shorts = struct.unpack("%dh" % count, chunk)
        sum_squares = sum(s*s for s in shorts)
        rms = math.sqrt(sum_squares / count)
        return rms < self.silence_threshold
