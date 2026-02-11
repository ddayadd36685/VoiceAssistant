import os
import platform
import subprocess
from pathlib import Path

def open_file(file_path: str) -> dict:
    """
    Open a file using the system default application.
    """
    path = Path(file_path).resolve()
    
    if not path.exists():
        return {"success": False, "message": f"File not found: {file_path}"}
        
    try:
        if platform.system() == 'Windows':
            os.startfile(str(path))
        elif platform.system() == 'Darwin':  # macOS
            subprocess.call(('open', str(path)))
        else:  # linux variants
            subprocess.call(('xdg-open', str(path)))
            
        return {"success": True, "message": f"Opened {file_path}", "resolved_path": str(path)}
    except Exception as e:
        return {"success": False, "message": str(e)}
