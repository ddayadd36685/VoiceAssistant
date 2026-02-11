import os
import sys
import numpy as np
import re
from pathlib import Path
from typing import List, Optional

import yaml
try:
    from .logger import get_logger
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from voice_assistant.logger import get_logger

class ASR:
    def __init__(self):
        self.logger = get_logger(__name__)
        self._hotwords_cache_text: str = ""
        self._hotwords_cache_mtime: Optional[float] = None
        
        try:
            import sherpa_onnx
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "未找到 sherpa-onnx 模块。请运行: .venv\\Scripts\\pip install sherpa-onnx"
            ) from e

        # Model paths
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "voice_assistant", "models", "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23")
        
        if not os.path.exists(base_dir):
             raise RuntimeError(f"Sherpa model not found at {base_dir}. Please run download_sherpa_model.py")

        self.logger.info(f"Loading Sherpa-ONNX model from {base_dir}...")
        
        self.hotwords_score = 2.5 # 默认加分
        
        tokens_path = os.path.join(base_dir, "tokens.txt")
        encoder_path = os.path.join(base_dir, "encoder-epoch-99-avg-1.onnx")
        decoder_path = os.path.join(base_dir, "decoder-epoch-99-avg-1.onnx")
        joiner_path = os.path.join(base_dir, "joiner-epoch-99-avg-1.onnx")

        self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=tokens_path,
            encoder=encoder_path,
            decoder=decoder_path,
            joiner=joiner_path,
            num_threads=1,
            sample_rate=16000,
            feature_dim=80,
            decoding_method="modified_beam_search",
            hotwords_file="", # Optional: can load from file
            hotwords_score=self.hotwords_score
        )
        self.logger.info("Sherpa-ONNX model loaded.")

    def _load_hotwords_from_file_config(self) -> List[str]:
        config_path = Path(__file__).resolve().parents[1] / "mcp_config" / "file_config.yaml"
        if not config_path.exists():
            return []

        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return []

        files = data.get("files", [])
        if not isinstance(files, list):
            return []

        keywords: List[str] = []
        seen = set()
        for item in files:
            if not isinstance(item, dict):
                continue
            kws = item.get("keywords", [])
            if isinstance(kws, str):
                kws = [kws]
            if not isinstance(kws, list):
                continue
            for kw in kws:
                if not isinstance(kw, str):
                    continue
                kw = kw.strip()
                if not kw:
                    continue
                if not re.search(r"[\u4e00-\u9fff]", kw):
                    continue
                k_norm = kw.lower()
                if k_norm in seen:
                    continue
                seen.add(k_norm)
                keywords.append(kw)
        return keywords

    def _get_hotwords_text(self) -> str:
        config_path = Path(__file__).resolve().parents[1] / "mcp_config" / "file_config.yaml"
        mtime: Optional[float]
        try:
            mtime = config_path.stat().st_mtime if config_path.exists() else None
        except Exception:
            mtime = None

        if mtime is not None and self._hotwords_cache_mtime == mtime:
            return self._hotwords_cache_text

        base_hotwords = ["打开", "开启", "帮我打开", "打开一下"]
        config_hotwords = self._load_hotwords_from_file_config()
        combined = []
        seen = set()
        for w in base_hotwords + config_hotwords:
            w = w.strip()
            if not w:
                continue
            w_norm = w.lower()
            if w_norm in seen:
                continue
            seen.add(w_norm)
            combined.append(w)

        text = " ".join(combined)
        self._hotwords_cache_text = text
        self._hotwords_cache_mtime = mtime
        return text

    def transcribe(self, audio_data: bytes) -> str:
        """
        Transcribe audio data (16kHz, mono, int16) to text using Sherpa-ONNX.
        Note: Although Sherpa supports streaming, we are using it in a 'batch-like' mode here
        to fit the existing interface.
        """
        self.logger.info(f"Transcribing {len(audio_data)} bytes of audio...")
        
        try:
            # Sherpa-ONNX expects float32 samples normalized to [-1, 1]
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            stream = self.recognizer.create_stream(hotwords=self._get_hotwords_text())
            stream.accept_waveform(16000, samples)
            stream.input_finished() # Tell the stream no more audio is coming
            
            while self.recognizer.is_ready(stream):
                self.recognizer.decode_stream(stream)
            
            # 使用 recognizer.get_result(stream) 获取结果
            # 注意：sherpa-onnx 1.9+ 版本 get_result 可能直接返回 string，或者返回对象
            # 根据报错 'str' object has no attribute 'text'，说明直接返回了字符串
            text = self.recognizer.get_result(stream).strip()
            self.logger.info(f"ASR Result: {text}")
            return text
            
        except Exception as e:
            self.logger.error(f"ASR Transcription failed: {e}", exc_info=True)
            return ""
