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
        
        self._apply_config()
        
        # Check if we have custom keywords
        if hasattr(self, 'config_keywords') and self.config_keywords:
            custom_kw_path = Path(__file__).resolve().parents[1] / "mcp_config" / "custom_keywords.txt"
            # Ensure mcp_config exists (it should, but just in case)
            custom_kw_path.parent.mkdir(parents=True, exist_ok=True)
            
            if self._generate_custom_keywords(self.config_keywords, str(custom_kw_path)):
                keywords_path = str(custom_kw_path)
                self.logger.info(f"Using custom keywords from {keywords_path}")
            else:
                self.logger.warning("Failed to use custom keywords, falling back to default.")

        if not os.path.exists(encoder_path):
            self.logger.error(f"KWS model not found at {base_dir}. Please run download_kws_model.py")
            self.spotter = None
            return

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
        
        config_keywords = kws.get("keywords", [])
        if isinstance(config_keywords, str):
            config_keywords = [p.strip() for p in config_keywords.replace("，", ",").split(",") if p.strip()]
        elif isinstance(config_keywords, list):
            config_keywords = [str(p).strip() for p in config_keywords if str(p).strip()]
        else:
            config_keywords = []

        self.config_keywords = config_keywords
        
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
    
    def _generate_custom_keywords(self, keywords: list, output_path: str) -> bool:
        try:
            import pypinyin
        except ImportError:
            self.logger.error("pypinyin not installed. Cannot generate custom keywords.")
            return False

        lines = []
        for kw in keywords:
            kw = str(kw).strip()
            if not kw:
                continue
            
            # Convert to pinyin: initials and finals
            # strict=False allows handling some edge cases better
            initials = pypinyin.pinyin(kw, style=pypinyin.Style.INITIALS, strict=False)
            finals = pypinyin.pinyin(kw, style=pypinyin.Style.FINALS_TONE, strict=False)
            
            phones = []
            for i_list, f_list in zip(initials, finals):
                i = i_list[0].strip()
                f = f_list[0].strip()
                if i:
                    phones.append(i)
                if f:
                    phones.append(f)
            
            if phones:
                phone_str = " ".join(phones)
                lines.append(f"{phone_str} @{kw}")
        
        if not lines:
            return False
            
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return True
        except Exception as e:
            self.logger.error(f"Failed to write custom keywords: {e}")
            return False

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
