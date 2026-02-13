import os
import sys
import numpy as np
import re
from pathlib import Path
from typing import List, Optional

import yaml
try:
    from .logger import get_logger
    from .mcp_client import ensure_mcp_config_files
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from voice_assistant.logger import get_logger
    from voice_assistant.mcp_client import ensure_mcp_config_files

class ASRBackend:
    def transcribe(self, audio_data: bytes) -> str:
        raise NotImplementedError

class SherpaASR(ASRBackend):
    def __init__(self, config: dict):
        self.logger = get_logger(__name__)
        self._hotwords_cache_text: str = ""
        self._hotwords_cache_mtime: Optional[float] = None
        
        try:
            import sherpa_onnx
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "未找到 sherpa-onnx 模块。请运行: .venv\\Scripts\\pip install sherpa-onnx"
            ) from e

        default_base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "voice_assistant", "models", "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23")
        base_dir = config.get("model_path", default_base_dir)
        
        if not os.path.isabs(base_dir):
            base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), base_dir)

        if not os.path.exists(base_dir):
             if base_dir != default_base_dir and os.path.exists(default_base_dir):
                 self.logger.warning(f"Configured model path {base_dir} not found. Falling back to default: {default_base_dir}")
                 base_dir = default_base_dir
             else:
                 raise RuntimeError(f"Sherpa model not found at {base_dir}. Please run download_sherpa_model.py")

        self.logger.info(f"Loading Sherpa-ONNX model from {base_dir}...")
        
        self.hotwords_score = 2.5
        
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
            hotwords_file="",
            hotwords_score=self.hotwords_score
        )
        self.logger.info("Sherpa-ONNX model loaded.")

    def _load_hotwords_from_file_config(self) -> List[str]:
        config_path = ensure_mcp_config_files().get("file_config") or (Path(__file__).resolve().parents[1] / "mcp_config" / "file_config.yaml")
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
        config_path = ensure_mcp_config_files().get("file_config") or (Path(__file__).resolve().parents[1] / "mcp_config" / "file_config.yaml")
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
        self.logger.info(f"Transcribing {len(audio_data)} bytes with Sherpa...")
        try:
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            stream = self.recognizer.create_stream(hotwords=self._get_hotwords_text())
            stream.accept_waveform(16000, samples)
            stream.input_finished()
            
            while self.recognizer.is_ready(stream):
                self.recognizer.decode_stream(stream)
            
            text = self.recognizer.get_result(stream).strip()
            self.logger.info(f"Sherpa Result: {text}")
            return text
        except Exception as e:
            self.logger.error(f"Sherpa transcription failed: {e}", exc_info=True)
            return ""

class FunASRBackend(ASRBackend):
    def __init__(self, config: dict):
        self.logger = get_logger(__name__)
        try:
            from funasr import AutoModel
        except ModuleNotFoundError as e:
            missing = getattr(e, "name", "") or ""
            if missing in ("torchaudio", "torch"):
                raise RuntimeError(
                    "FunASR 依赖 torch/torchaudio，但当前环境缺少它们。请先安装 torch 和 torchaudio。"
                ) from e
            raise RuntimeError("未找到 funasr。请运行 pip install funasr modelscope") from e
        except ImportError as e:
            raise RuntimeError("未找到 funasr。请运行 pip install funasr modelscope") from e
            
        model_name = config.get("model_name", "iic/SenseVoiceSmall")
        self.logger.info(f"Loading FunASR model: {model_name}...")
        
        try:
            self.model = AutoModel(
                model=model_name,
                trust_remote_code=True,
                device="cuda" if config.get("device") == "cuda" else "cpu"
            )
        except Exception as e:
            self.logger.error(f"Failed to load FunASR model: {e}")
            raise e
            
        self.logger.info("FunASR model loaded.")

    def transcribe(self, audio_data: bytes) -> str:
        self.logger.info(f"Transcribing {len(audio_data)} bytes with FunASR...")
        try:
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            res = self.model.generate(
                input=samples,
                cache={},
                language="auto",
                use_itn=True,
                batch_size_s=60
            )
            if res and isinstance(res, list) and len(res) > 0:
                text = res[0].get("text", "")
                clean_text = re.sub(r"<\|.*?\|>", "", text).strip()
                self.logger.info(f"FunASR Result: {clean_text} (raw: {text})")
                return clean_text
            return ""
        except Exception as e:
            self.logger.error(f"FunASR transcription failed: {e}", exc_info=True)
            return ""

class ASR:
    def __init__(self):
        self.logger = get_logger(__name__)
        self.config = self._load_config()
        
        asr_config = self.config.get("asr", {})
        self.provider = asr_config.get("provider", "sherpa")
        
        self.logger.info(f"Initializing ASR provider: {self.provider}")

        try:
            if self.provider == "funasr":
                self.backend = FunASRBackend(asr_config.get("funasr", {}))
            else:
                self.backend = SherpaASR(asr_config.get("sherpa", {}))
        except Exception as e:
            self.logger.error(f"ASR provider init failed ({self.provider}): {e}", exc_info=True)
            if self.provider != "sherpa":
                self.provider = "sherpa"
                self.backend = SherpaASR(asr_config.get("sherpa", {}))
            else:
                raise

    def _load_config(self) -> dict:
        config_path = Path(__file__).resolve().parents[1] / "config.yaml"
        if not config_path.exists():
            return {}
        try:
            return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

    def transcribe(self, audio_data: bytes) -> str:
        return self.backend.transcribe(audio_data)
