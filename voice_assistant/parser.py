import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
from .logger import get_logger
import yaml


class Parser:
    def __init__(self):
        self.logger = get_logger(__name__)
        self.patterns = [
            r"(?:打开|开启|帮我打开)\s*(?P<target>.+)",
            r"(?P<target>.+)\s*(?:打开一下|打开)"
        ]
        self.web_patterns = [
            r"(?:打开(?:网页|网站|网址)|访问|进入)\s*(?P<target>.+)",
            r"(?P<target>.+)\s*(?:网站|网页|官网)$"
        ]

    def _load_keywords(self, config_path: Path, root_key: str) -> List[str]:
        if not config_path.exists():
            return []

        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return []

        items = data.get(root_key, [])
        if not isinstance(items, list):
            return []

        keywords: List[str] = []
        seen = set()
        for item in items:
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
                k_norm = kw.lower()
                if k_norm in seen:
                    continue
                seen.add(k_norm)
                keywords.append(kw)
        return keywords

    def _load_file_keywords(self) -> List[str]:
        config_path = Path(__file__).resolve().parents[1] / "mcp_config" / "file_config.yaml"
        return self._load_keywords(config_path, "files")

    def _load_web_keywords(self) -> List[str]:
        config_path = Path(__file__).resolve().parents[1] / "mcp_config" / "web_config.yaml"
        return self._load_keywords(config_path, "websites")

    def _load_web_items(self) -> List[Dict[str, Any]]:
        config_path = Path(__file__).resolve().parents[1] / "mcp_config" / "web_config.yaml"
        if not config_path.exists():
            return []
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return []
        sites = data.get("websites", [])
        if not isinstance(sites, list):
            return []
        return [s for s in sites if isinstance(s, dict)]

    def _normalize_to_allowed_keyword(self, target: str, allowed_keywords: List[str]) -> Optional[str]:
        target_norm = target.strip().lower()
        if not target_norm:
            return None
        for kw in allowed_keywords:
            kw_norm = kw.strip().lower()
            if not kw_norm:
                continue
            if kw_norm in target_norm or target_norm in kw_norm:
                return kw
        return None

    def _normalize_web_to_canonical(self, target: str, web_items: List[Dict[str, Any]]) -> Optional[str]:
        t_norm = target.strip().lower()
        if not t_norm:
            return None
        for item in web_items:
            kws = item.get("keywords", [])
            if isinstance(kws, str):
                kws = [kws]
            if not isinstance(kws, list) or not kws:
                continue
            canonical = str(kws[0]).strip()
            for kw in kws:
                if not isinstance(kw, str):
                    continue
                k_norm = kw.strip().lower()
                if not k_norm:
                    continue
                if k_norm in t_norm or t_norm in k_norm:
                    return canonical
        return None

    def _load_api_key(self) -> Optional[str]:
        key = os.getenv("DEEPSEEK_API_KEY")
        if key:
            return key

        env_path = Path(__file__).resolve().parents[1] / ".env"
        if not env_path.exists():
            return None

        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "DEEPSEEK_API_KEY" and v:
                    os.environ["DEEPSEEK_API_KEY"] = v
                    return v
        except Exception:
            return None

        return None

    def _extract_json(self, content: str) -> Optional[Dict[str, str]]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        try:
            data = json.loads(text)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        intent = data.get("intent")
        target = data.get("target", "")
        if intent not in ("open_file", "open_web", "unknown"):
            return None
        if not isinstance(target, str):
            return None
        return {"intent": intent, "target": target}

    def _llm_parse(self, text: str) -> Optional[Dict[str, str]]:
        if os.getenv("VOICE_ASSISTANT_DISABLE_LLM", "").lower() in ("1", "true", "yes"):
            return None

        file_keywords = self._load_file_keywords()
        web_keywords = self._load_web_keywords()
        web_items = self._load_web_items()
        if not file_keywords and not web_keywords:
            return None

        api_key = self._load_api_key()
        if not api_key:
            return None

        url = "https://api.deepseek.com/v1/chat/completions"
        allowed_file_text = "\n".join(f"- {kw}" for kw in file_keywords)
        allowed_web_text = "\n".join(f"- {kw}" for kw in web_keywords)
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "你是意图解析器。只输出JSON，格式为 {\"intent\":\"open_file|open_web|unknown\",\"target\":\"...\"}。如果 intent=open_file，则 target 必须严格从文件允许列表中选择一个；如果 intent=open_web，则 target 必须严格从网页允许列表中选择一个；否则返回 unknown。",
                },
                {"role": "user", "content": f"文件允许列表：\n{allowed_file_text}\n\n网页允许列表：\n{allowed_web_text}\n\n用户话语：{text}"},
            ],
            "temperature": 0,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp_text = resp.read().decode("utf-8")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception) as e:
            self.logger.error(f"LLM parse failed: {e}")
            return None

        try:
            data = json.loads(resp_text)
            content = data["choices"][0]["message"]["content"]
        except Exception:
            return None

        parsed = self._extract_json(content)
        if not parsed:
            return None
        intent = parsed["intent"]
        target = parsed.get("target", "")
        if intent == "open_file":
            normalized = self._normalize_to_allowed_keyword(target, file_keywords)
            if not normalized:
                return {"intent": "unknown", "target": ""}
            return {"intent": "open_file", "target": normalized}
        if intent == "open_web":
            normalized = self._normalize_web_to_canonical(target, web_items)
            if not normalized:
                return {"intent": "unknown", "target": ""}
            return {"intent": "open_web", "target": normalized}
        return {"intent": "unknown", "target": ""}
        
    def parse(self, text: str) -> Dict[str, str]:
        text = text.strip()
        self.logger.debug(f"Parsing text: {text}")

        file_keywords = self._load_file_keywords()
        web_items = self._load_web_items()

        has_web_hint = bool(re.search(r"(网页|网站|网址|官网|访问|进入)", text))
        if has_web_hint:
            for pattern in self.web_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    target = match.group("target").strip()
                    target = re.sub(r"[。.！!]+$", "", target)
                    normalized = self._normalize_web_to_canonical(target, web_items)
                    if normalized:
                        self.logger.info(f"Parsed intent: open_web, target: {normalized}")
                        return {"intent": "open_web", "target": normalized}
        
        for pattern in self.patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                target = match.group("target").strip()
                # Remove common punctuation at the end
                target = re.sub(r"[。.！!]+$", "", target)
                # Remove potential suffix command words if caught in target (e.g. "打开 file 打开一下")
                target = re.sub(r"\s*(?:打开一下|打开)$", "", target)

                normalized_file = self._normalize_to_allowed_keyword(target, file_keywords)
                if normalized_file:
                    self.logger.info(f"Parsed intent: open_file, target: {normalized_file}")
                    return {"intent": "open_file", "target": normalized_file}
                normalized_web = self._normalize_web_to_canonical(target, web_items)
                if normalized_web:
                    self.logger.info(f"Parsed intent: open_web, target: {normalized_web}")
                    return {"intent": "open_web", "target": normalized_web}
        llm_res = self._llm_parse(text)
        if llm_res:
            self.logger.info(f"Parsed intent (llm): {llm_res['intent']}, target: {llm_res['target']}")
            return llm_res

        self.logger.info("Parsed intent: unknown")
        return {"intent": "unknown", "target": ""}
