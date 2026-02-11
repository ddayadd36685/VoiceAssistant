import webbrowser
from urllib.parse import urlparse

def open_web(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"success": False, "message": f"Unsupported URL scheme: {parsed.scheme}"}
    if not parsed.netloc:
        return {"success": False, "message": f"Invalid URL: {url}"}
    try:
        opened = webbrowser.open(url)
        if not opened:
            return {"success": False, "message": f"Failed to open URL: {url}"}
        return {"success": True, "message": f"Opened {url}", "resolved_url": url}
    except Exception as e:
        return {"success": False, "message": str(e)}
