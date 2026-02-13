import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
from .logger import get_logger
from .mcp_client import ensure_mcp_config_files
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
        config_path = ensure_mcp_config_files().get("file_config") or (Path(__file__).resolve().parents[1] / "mcp_config" / "file_config.yaml")
        return self._load_keywords(config_path, "files")

    def _load_web_keywords(self) -> List[str]:
        config_path = ensure_mcp_config_files().get("web_config") or (Path(__file__).resolve().parents[1] / "mcp_config" / "web_config.yaml")
        return self._load_keywords(config_path, "websites")

    def _load_web_items(self) -> List[Dict[str, Any]]:
        config_path = ensure_mcp_config_files().get("web_config") or (Path(__file__).resolve().parents[1] / "mcp_config" / "web_config.yaml")
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

    def _extract_json(self, content: str) -> Optional[Dict[str, Any]]:
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
            
        # Support both old and new format for backward compatibility
        actions = []
        if "actions" in data and isinstance(data["actions"], list):
            for act in data["actions"]:
                if isinstance(act, dict) and "intent" in act and "target" in act:
                    actions.append(act)
        elif "intent" in data and "target" in data:
             actions.append({"intent": data["intent"], "target": data["target"]})
             
        reply = data.get("reply", "")
        
        # Validate intents
        valid_actions = []
        for act in actions:
            intent = act.get("intent")
            if intent in ("open_file", "open_web", "chat", "unknown"):
                valid_actions.append(act)
                
        if not valid_actions and not reply:
            return None
            
        return {"actions": valid_actions, "reply": reply}

    def parse(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        self.logger.debug(f"Parsing text: {text}")

        file_keywords = self._load_file_keywords()
        web_keywords = self._load_web_keywords()
        web_items = self._load_web_items()

        disable_llm = (os.getenv("VOICE_ASSISTANT_DISABLE_LLM") or "").strip().lower() in ("1", "true", "yes", "y")
        if disable_llm:
            notice = "提示：大模型不可用，已使用离线规则解析。"
            actions = []
            for pat in self.web_patterns:
                m = re.search(pat, text)
                if not m:
                    continue
                raw_target = (m.groupdict().get("target") or "").strip()
                norm = self._normalize_web_to_canonical(raw_target, web_items)
                if norm:
                    actions.append({"intent": "open_web", "target": norm})
                    # For basic matching, we might stop at first match or continue. 
                    # Let's stop to match previous behavior or just allow one.
                    break

            if not actions:
                for pat in self.patterns:
                    m = re.search(pat, text)
                    if not m:
                        continue
                    raw_target = (m.groupdict().get("target") or "").strip()
                    norm = self._normalize_to_allowed_keyword(raw_target, file_keywords)
                    if norm:
                        actions.append({"intent": "open_file", "target": norm})
                        break
            
            if not actions:
                actions.append({"intent": "unknown", "target": ""})

            if actions and actions[0].get("intent") in ("open_file", "open_web"):
                return {"actions": actions, "reply": notice}
            return {"actions": actions, "reply": f"{notice}（如果你希望更准确的理解与闲聊，请配置 DEEPSEEK_API_KEY）"}

        api_key = self._load_api_key()
        if not api_key:
            self.logger.warning("No API key found for LLM parser, falling back to basic matching")
            return {"actions": [{"intent": "chat", "target": ""}], "reply": "抱歉，我还没配置好大模型，现在只能听懂一些简单的指令。"}

        url = "https://api.deepseek.com/v1/chat/completions"
        allowed_file_text = "\n".join(f"- {kw}" for kw in file_keywords)
        allowed_web_text = "\n".join(f"- {kw}" for kw in web_keywords)
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": """你是语音助手的核心解析与对话模块。
请根据用户的话语，判断其意图并生成回复。必须输出JSON格式：
{
  "actions": [
    {
      "intent": "open_file" | "open_web" | "chat" | "unknown",
      "target": "对应列表中的关键词，如果是chat则为空"
    }
  ],
  "reply": "你对用户说的回复语"
}

意图规则：
1. open_file: 用户想打开本地文件/应用。target 必须严格从【文件允许列表】中选择最匹配的一个。
2. open_web: 用户想打开网页。target 必须严格从【网页允许列表】中选择最匹配的一个关键词。
3. chat: 用户在闲聊、提问或不需要操作系统的行为。你需要给出自然、亲切、简短的回复。
4. unknown: 无法理解的意图。
5. actions 列表可以包含多个任务（例如用户说“打开A和B”）。如果是纯闲聊，actions 列表可以只包含一个 chat intent，或者为空。

回复语规则：
- 如果是打开操作，回复语应简洁，如“好的，正在为您打开[target]”。
- 如果是闲聊，回复语应像朋友一样自然，字数不要太多（适合语音播报）。
"""
                },
                {"role": "user", "content": f"文件允许列表：\n{allowed_file_text}\n\n网页允许列表：\n{allowed_web_text}\n\n用户话语：{text}"},
            ],
            "temperature": 0.7,
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
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_text = resp.read().decode("utf-8")
                data = json.loads(resp_text)
                content = data["choices"][0]["message"]["content"]
                parsed = self._extract_json(content)
                
                if parsed:
                    valid_actions = []
                    for act in parsed.get("actions", []):
                        # 归一化 target
                        if act["intent"] == "open_file":
                            norm = self._normalize_to_allowed_keyword(act["target"], file_keywords)
                            if norm:
                                act["target"] = norm
                                valid_actions.append(act)
                        elif act["intent"] == "open_web":
                            norm = self._normalize_web_to_canonical(act["target"], web_items)
                            if norm:
                                act["target"] = norm
                                valid_actions.append(act)
                        else:
                            # chat or unknown
                            valid_actions.append(act)
                    
                    parsed["actions"] = valid_actions
                    
                    # Log actions
                    action_strs = [f"{a['intent']}:{a['target']}" for a in valid_actions]
                    self.logger.info(f"LLM Parsed Actions: {', '.join(action_strs)}")
                    return parsed
        except Exception as e:
            self.logger.error(f"LLM parse failed: {e}")
        
        return {"actions": [{"intent": "chat", "target": ""}], "reply": "抱歉，我现在有点走神，没听清你在说什么。"}
