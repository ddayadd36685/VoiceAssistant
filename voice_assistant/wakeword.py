import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from .logger import get_logger

try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None

class WakeWordDetector:
    def __init__(self, sensitivity=0.5):
        self.logger = get_logger(__name__)
        self.last_trigger_time = 0.0
        self.cooldown_sec = 2.0
        self.keywords_score = 1.0
        self.keywords_threshold = 0.25
        
        if not sherpa_onnx:
            self.logger.error("sherpa-onnx not found. WakeWordDetector disabled.")
            self.spotter = None
            return

        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "voice_assistant",
            "models",
            "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01",
        )
        
        encoder_path = os.path.join(base_dir, "encoder-epoch-12-avg-2-chunk-16-left-64.onnx")
        decoder_path = os.path.join(base_dir, "decoder-epoch-12-avg-2-chunk-16-left-64.onnx")
        joiner_path = os.path.join(base_dir, "joiner-epoch-12-avg-2-chunk-16-left-64.onnx")
        tokens_path = os.path.join(base_dir, "tokens.txt")
        keywords_path = os.path.join(base_dir, "keywords.txt")
        
        if not os.path.exists(encoder_path):
            self.logger.error(f"KWS model not found at {base_dir}. Please run download_kws_model.py")
            self.spotter = None
            return

        self._apply_config()
        
        self.spotter = sherpa_onnx.KeywordSpotter(
            tokens=tokens_path,
            encoder=encoder_path,
            decoder=decoder_path,
            joiner=joiner_path,
            keywords_file=keywords_path,
            num_threads=1,
            sample_rate=16000,
            feature_dim=80,
            keywords_score=self.keywords_score,
            keywords_threshold=self.keywords_threshold,
        )
        self.stream = self.spotter.create_stream()
        self.logger.info("WakeWordDetector initialized (Sherpa-ONNX KWS).")

    def _apply_config(self):
        config_path = Path(__file__).resolve().parents[1] / "config.yaml"
        if not config_path.exists():
            return
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return
        kws = data.get("kws", {})
        if not isinstance(kws, dict):
            return
        keywords_score = kws.get("keywords_score", self.keywords_score)
        keywords_threshold = kws.get("keywords_threshold", self.keywords_threshold)
        cooldown_sec = kws.get("cooldown_sec", self.cooldown_sec)
        try:
            self.keywords_score = float(keywords_score)
        except Exception:
            pass
        try:
            self.keywords_threshold = float(keywords_threshold)
        except Exception:
            pass
        try:
            self.cooldown_sec = float(cooldown_sec)
        except Exception:
            pass
    
    def process(self, chunk: bytes) -> Optional[str]:
        """
        Process audio chunk and return keyword string if detected, else None.
        Changed return type from bool to Optional[str].
        """
        if not self.spotter or not chunk:
            return None
            
        now = time.time()
        if now - self.last_trigger_time < self.cooldown_sec:
            return None

        # Convert int16 bytes -> float32 normalized
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        
        self.stream.accept_waveform(16000, samples)
        
        while self.spotter.is_ready(self.stream):
            self.spotter.decode_stream(self.stream)
            keyword = self.spotter.get_result(self.stream).strip()
            if keyword:
                self.logger.info(f"Wake Word Detected: {keyword}")
                self.last_trigger_time = now
                self.stream = self.spotter.create_stream()
                return keyword
                
        return None
