from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .logger import get_logger
from mcptool import open_file, open_web

def ensure_mcp_config_files(project_root: Optional[Path] = None) -> Dict[str, Path]:
    root = project_root or Path(__file__).resolve().parents[1]
    mcp_dir = root / "mcp_config"
    try:
        mcp_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return {"dir": mcp_dir, "file_config": mcp_dir / "file_config.yaml", "web_config": mcp_dir / "web_config.yaml"}

    file_config = mcp_dir / "file_config.yaml"
    web_config = mcp_dir / "web_config.yaml"

    if not file_config.exists():
        try:
            text = yaml.safe_dump(
                {"files": []},
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
            file_config.write_text(text, encoding="utf-8")
        except Exception:
            pass

    if not web_config.exists():
        try:
            text = yaml.safe_dump(
                {"websites": []},
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
            web_config.write_text(text, encoding="utf-8")
        except Exception:
            pass

    return {"dir": mcp_dir, "file_config": file_config, "web_config": web_config}

class MCPClient:
    def __init__(self):
        self.logger = get_logger(__name__)
        ensure_mcp_config_files()

    def _load_file_config(self) -> List[Dict[str, Any]]:
        config_path = ensure_mcp_config_files().get("file_config") or (Path(__file__).resolve().parents[1] / "mcp_config" / "file_config.yaml")
        if not config_path.exists():
            self.logger.warning("file_config.yaml not found. No files are allowed to open.")
            return []

        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            self.logger.error(f"Failed to read file_config.yaml: {e}")
            return []

        files = data.get("files", [])
        if not isinstance(files, list):
            self.logger.error("Invalid file_config.yaml format: files must be a list.")
            return []

        return files

    def _load_web_config(self) -> List[Dict[str, Any]]:
        config_path = ensure_mcp_config_files().get("web_config") or (Path(__file__).resolve().parents[1] / "mcp_config" / "web_config.yaml")
        if not config_path.exists():
            self.logger.warning("web_config.yaml not found. No websites are allowed to open.")
            return []

        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            self.logger.error(f"Failed to read web_config.yaml: {e}")
            return []

        sites = data.get("websites", [])
        if not isinstance(sites, list):
            self.logger.error("Invalid web_config.yaml format: websites must be a list.")
            return []

        return sites

    def _match_target_to_path(self, target: str, files: List[Dict[str, Any]]) -> Optional[str]:
        target_norm = target.strip().lower()
        if not target_norm:
            return None

        for item in files:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            keywords = item.get("keywords", [])

            if isinstance(keywords, str):
                keywords = [keywords]

            if not isinstance(keywords, list):
                continue

            for kw in keywords:
                if not isinstance(kw, str):
                    continue
                kw_norm = kw.strip().lower()
                if not kw_norm:
                    continue
                if kw_norm in target_norm or target_norm in kw_norm:
                    return path

        return None

    def _match_target_to_url(self, target: str, sites: List[Dict[str, Any]]) -> Optional[str]:
        target_norm = target.strip().lower()
        if not target_norm:
            return None

        for item in sites:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            keywords = item.get("keywords", [])

            if isinstance(keywords, str):
                keywords = [keywords]

            if not isinstance(keywords, list):
                continue

            for kw in keywords:
                if not isinstance(kw, str):
                    continue
                kw_norm = kw.strip().lower()
                if not kw_norm:
                    continue
                if kw_norm in target_norm or target_norm in kw_norm:
                    return url

        return None

    def execute(self, intent: str, target: str) -> bool:
        """
        Execute the parsed intent using MCP tools.
        """
        if intent == "unknown":
            self.logger.info("Ignoring unknown intent.")
            return False

        if intent not in ("open_file", "open_web"):
            self.logger.warning(f"Unsupported intent: {intent}")
            return False
            
        self.logger.info(f"Executing MCP tool for target: {target}")

        if intent == "open_file":
            files = self._load_file_config()
            file_path = self._match_target_to_path(target, files)

            if not file_path:
                self.logger.warning(f"Target not allowed or not found in config: {target}")
                return False

            path_obj = Path(str(file_path))
            if not path_obj.is_absolute():
                self.logger.warning(f"Configured path must be absolute: {file_path}")
                return False

            result = open_file(file_path)
            if result["success"]:
                self.logger.info(f"Successfully opened: {file_path}")
                return True
            else:
                self.logger.error(f"Failed to open file: {result['message']}")
                return False

        sites = self._load_web_config()
        url = self._match_target_to_url(target, sites)
        if not url:
            self.logger.warning(f"Target not allowed or not found in config: {target}")
            return False

        result = open_web(url)
        if result["success"]:
            self.logger.info(f"Successfully opened: {url}")
            return True
        else:
            self.logger.error(f"Failed to open web: {result['message']}")
            return False
