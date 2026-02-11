import os
import tarfile
import urllib.request
from rich.console import Console
from rich.progress import Progress

console = Console()

# Sherpa-ONNX KWS Model (Zipformer WenetSpeech 3.3M)
MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01.tar.bz2"
MODEL_DIR = os.path.join("voice_assistant", "models")
FILE_NAME = MODEL_URL.split("/")[-1]
TARGET_PATH = os.path.join(MODEL_DIR, FILE_NAME)
EXTRACT_DIR = os.path.join(MODEL_DIR, "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01")

def download_kws_model():
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)
        
    if os.path.exists(os.path.join(EXTRACT_DIR, "encoder-epoch-12-avg-2.onnx")):
        console.print("[green]KWS Model already exists, skipping download.[/green]")
        return

    console.print(f"Downloading KWS model from {MODEL_URL}...")
    
    try:
        with Progress() as progress:
            task = progress.add_task("[cyan]Downloading...", total=None)
            
            def report(block_num, block_size, total_size):
                progress.update(task, total=total_size, completed=block_num * block_size)

            urllib.request.urlretrieve(MODEL_URL, TARGET_PATH, reporthook=report)
            
        console.print("[green]Download complete.[/green]")
        
        console.print("Extracting...")
        with tarfile.open(TARGET_PATH, "r:bz2") as tar:
            tar.extractall(path=MODEL_DIR)
            
        console.print(f"[green]Model extracted to {EXTRACT_DIR}[/green]")
        
        # Cleanup
        os.remove(TARGET_PATH)
        
    except Exception as e:
        console.print(f"[bold red]Error downloading/extracting model: {e}[/bold red]")

def create_keywords_file():
    kw_path = os.path.join(EXTRACT_DIR, "keywords.txt")
    if os.path.exists(kw_path):
        console.print(f"[yellow]keywords.txt already exists at {kw_path}, keeping it.[/yellow]")
        return

    # Create default keywords file
    # Format: id string score
    # But for Sherpa KeywordSpotter, we usually provide keywords directly or a file with format:
    # "keyword  threshold"
    # Actually for sherpa-onnx python api, we can pass keywords string directly OR file.
    # The file format expected by `keywords_file` is typically one keyword per line, maybe with score.
    # Let's verify standard format: "你好小梦"
    # Or "@你好小梦" for boosting?
    # Simpler: just write a helper file, but we might pass keywords programmatically.
    
    content = """你好小梦 2.0
小梦同学 2.0
Hey Assistant 2.0
"""
    if not os.path.exists(EXTRACT_DIR):
        os.makedirs(EXTRACT_DIR, exist_ok=True)
        
    with open(kw_path, "w", encoding="utf-8") as f:
        f.write(content)
    console.print(f"[green]Created keywords.txt at {kw_path}[/green]")

if __name__ == "__main__":
    download_kws_model()
    create_keywords_file()
