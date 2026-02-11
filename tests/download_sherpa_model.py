import os
import tarfile
import urllib.request
from rich.console import Console
from rich.progress import Progress

console = Console()

MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23.tar.bz2"
MODEL_DIR = os.path.join("voice_assistant", "models")
FILE_NAME = MODEL_URL.split("/")[-1]
TARGET_PATH = os.path.join(MODEL_DIR, FILE_NAME)

def download_model():
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)
        
    if os.path.exists(os.path.join(MODEL_DIR, "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23", "encoder-epoch-99-avg-1.onnx")):
        console.print("[green]Model already exists, skipping download.[/green]")
        return

    console.print(f"Downloading model from {MODEL_URL}...")
    
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
            
        console.print(f"[green]Model extracted to {MODEL_DIR}[/green]")
        
        # Cleanup
        os.remove(TARGET_PATH)
        
    except Exception as e:
        console.print(f"[bold red]Error downloading/extracting model: {e}[/bold red]")

if __name__ == "__main__":
    download_model()
