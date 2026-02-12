import sys
import time
import subprocess
import signal
import requests
from voice_assistant.ui.app import main as ui_main, RESTART_EXIT_CODE

SERVER_URL = "http://127.0.0.1:8000"
HEALTH_ENDPOINT = f"{SERVER_URL}/v1/health"

def get_asr_provider() -> str:
    try:
        import yaml
        from pathlib import Path
        config_path = Path(__file__).resolve().parent / "config.yaml"
        if not config_path.exists():
            return "sherpa"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return (config.get("asr", {}) or {}).get("provider", "sherpa")
    except Exception:
        return "sherpa"

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

def shutdown_backend(backend_process: subprocess.Popen):
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

def main():
    print("Starting Voice Assistant Application...")

    while True:
        backend_process = None
        started_by_launcher = False

        if backend_is_ready():
            print("Backend already running.")
        else:
            backend_process = start_backend()
            started_by_launcher = True

        exit_code = 0
        try:
            provider = get_asr_provider()
            timeout = 30
            if provider == "faster_whisper":
                timeout = 300
            elif provider == "funasr":
                timeout = 120
            else:
                timeout = 60

            if not wait_for_backend(timeout=timeout):
                print("Error: Backend failed to start within timeout.")
                exit_code = 1
            else:
                print("Backend ready. Launching UI...")
                exit_code = int(ui_main())

        except KeyboardInterrupt:
            print("\nApplication interrupted by user.")
            exit_code = 130

        finally:
            if started_by_launcher and backend_process is not None:
                print("Shutting down backend...")
                shutdown_backend(backend_process)
            print("Application cleanup complete.")

        if exit_code == RESTART_EXIT_CODE:
            if not started_by_launcher:
                print("Restart requested, but backend is already running. Please restart backend to apply ASR changes.")
                return 0
            print("Restart requested. Restarting application...")
            continue

        return exit_code

if __name__ == "__main__":
    raise SystemExit(main())
