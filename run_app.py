import sys
import time
import subprocess
import signal
import requests
from voice_assistant.ui.app import main as ui_main

SERVER_URL = "http://127.0.0.1:8000"
HEALTH_ENDPOINT = f"{SERVER_URL}/v1/health"

def backend_is_ready():
    try:
        resp = requests.get(HEALTH_ENDPOINT, timeout=1)
        return resp.status_code == 200
    except requests.RequestException:
        return False

def start_backend():
    print("Launching backend server...")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    cmd = [sys.executable, "-u", "run_server.py"]
    process = subprocess.Popen(cmd, creationflags=creationflags)
    return process

def wait_for_backend(timeout=30):
    start_time = time.time()
    print(f"Waiting for backend at {HEALTH_ENDPOINT}...")
    
    while time.time() - start_time < timeout:
        if backend_is_ready():
            print("Backend is ready!")
            return True
        time.sleep(0.5)
    
    return False

def main():
    print("Starting Voice Assistant Application...")
    
    backend_process = None
    started_by_launcher = False

    if backend_is_ready():
        print("Backend already running.")
    else:
        backend_process = start_backend()
        started_by_launcher = True
    
    try:
        if not wait_for_backend():
            print("Error: Backend failed to start within timeout.")
            return 1

        print("Backend ready. Launching UI...")
        return int(ui_main())
            
    except KeyboardInterrupt:
        print("\nApplication interrupted by user.")
        return 130
        
    finally:
        if started_by_launcher and backend_process is not None:
            print("Shutting down backend...")
            if backend_process.poll() is None:
                graceful_sent = False
                try:
                    if sys.platform.startswith("win") and hasattr(signal, "CTRL_BREAK_EVENT"):
                        backend_process.send_signal(signal.CTRL_BREAK_EVENT)
                        graceful_sent = True
                    else:
                        backend_process.send_signal(signal.SIGINT)
                        graceful_sent = True
                except Exception:
                    graceful_sent = False

                try:
                    backend_process.wait(timeout=6 if graceful_sent else 2)
                except subprocess.TimeoutExpired:
                    backend_process.terminate()
                    try:
                        backend_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        backend_process.kill()
        print("Application cleanup complete.")

if __name__ == "__main__":
    raise SystemExit(main())
