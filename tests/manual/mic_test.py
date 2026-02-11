import math
import os
import struct
import sys
import threading
import queue
import time

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from voice_assistant.audio_stream import MicrophoneStream
from voice_assistant.asr import ASR
from voice_assistant.vad_recorder import VadRecorder
from voice_assistant.wakeword import WakeWordDetector

console = Console()


def calculate_rms(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    count = len(chunk) // 2
    shorts = struct.unpack("%dh" % count, chunk)
    sum_squares = sum(s * s for s in shorts)
    return math.sqrt(sum_squares / count)


def main():
    console.print("[bold green]Microphone Test Tool[/bold green]")
    console.print("This tool will visualize the audio input energy, wakeword, VAD, and ASR.")
    console.print("Please speak loudly (or clap) to trigger wakeword...")
    console.print("Press Ctrl+C to stop.\n")

    try:
        wake = WakeWordDetector()
        wake_hold_sec = 1.2
        woke_until = 0.0

        vad = VadRecorder()
        max_silence_chunks = int(vad.silence_limit_sec * vad.chunks_per_sec)
        max_recording_chunks = int(10 * vad.chunks_per_sec)

        is_recording = False
        frames: list[bytes] = []
        silence_chunks = 0
        recording_started_at = 0.0
        last_recording_summary = ""
        asr_status_right = "[dim]LOADING[/dim]"
        asr_completed = 0
        asr_latest_text = ""
        asr_latest_time = 0.0

        asr = ASR()
        asr_status_right = "[dim]IDLE[/dim]"

        asr_queue: queue.Queue[bytes] = queue.Queue()
        asr_result_queue: queue.Queue[tuple[float, str, float]] = queue.Queue()

        def asr_worker():
            while True:
                audio_data = asr_queue.get()
                if audio_data is None:
                    return
                started = time.time()
                try:
                    text = asr.transcribe(audio_data)
                except Exception as e:
                    text = f"[ASR ERROR] {e}"
                finished = time.time()
                asr_result_queue.put((started, text, finished))

        worker_thread = threading.Thread(target=asr_worker, daemon=True)
        worker_thread.start()

        with MicrophoneStream() as stream:
            with Progress(
                TextColumn("[bold blue]{task.fields[label]}"),
                BarColumn(bar_width=40),
                TextColumn("{task.fields[right]}"),
                console=console,
                transient=True,
            ) as progress:
                mic_task = progress.add_task(
                    "Mic", total=10000, label="Mic", right="[yellow]0.00[/yellow]"
                )
                wake_task = progress.add_task(
                    "Wake",
                    total=10000,
                    label="Wake",
                    right="[dim]IDLE[/dim]",
                    visible=True,
                )
                vad_task = progress.add_task(
                    "VAD",
                    total=10000,
                    label="VAD",
                    right="[dim]IDLE[/dim]",
                    visible=True,
                )
                asr_task = progress.add_task(
                    "ASR",
                    total=10000,
                    label="ASR",
                    right=asr_status_right,
                    visible=True,
                )

                while True:
                    chunk = stream.read()
                    rms = calculate_rms(chunk)
                    display_val = min(rms, 10000)

                    now = time.time()
                    while True:
                        try:
                            started, text, finished = asr_result_queue.get_nowait()
                        except queue.Empty:
                            break
                        asr_latest_text = text or ""
                        asr_latest_time = finished
                        asr_status_right = f"[cyan]TEXT[/cyan]  {asr_latest_text[:80]}"
                        asr_completed = 10000
                    
                    # Update: process now returns Optional[str] (keyword or None)
                    triggered_keyword = wake.process(chunk)
                    if triggered_keyword:
                        woke_until = max(woke_until, now + wake_hold_sec)
                        if not is_recording:
                            is_recording = True
                            frames = []
                            # Prepend pre-roll if available (from stream history)
                            if hasattr(stream, 'get_pre_roll'):
                                frames.append(stream.get_pre_roll())
                            
                            frames.append(chunk)
                            silence_chunks = 0
                            recording_started_at = now
                            last_recording_summary = ""
                    
                    wake_ratio = 0.0
                    if woke_until > now:
                        wake_ratio = (woke_until - now) / wake_hold_sec
                    wake_level = int(10000 * max(0.0, min(1.0, wake_ratio)))
                    wake_state_text = "[dim]IDLE[/dim]"
                    if triggered_keyword:
                         wake_state_text = f"[bold red]WOKE: {triggered_keyword}[/bold red]"
                    elif wake_level > 0:
                        wake_state_text = "[bold red]WOKE (Holding)[/bold red]"

                    mic_state_text = "[dim]Quiet[/dim]"
                    if rms > 3000:
                        mic_state_text = "[red]LOUD[/red]"
                    elif rms > 500:
                        mic_state_text = "[green]Speaking[/green]"

                    vad_completed = 0
                    vad_right = "[dim]IDLE[/dim]"
                    if is_recording:
                        frames.append(chunk)
                        silent_now = vad._is_silent(chunk)
                        if silent_now:
                            silence_chunks += 1
                        else:
                            silence_chunks = 0

                        ratio = 0.0
                        if max_silence_chunks > 0:
                            ratio = silence_chunks / max_silence_chunks
                        vad_completed = int(10000 * max(0.0, min(1.0, ratio)))

                        elapsed = now - recording_started_at
                        if silent_now:
                            vad_right = (
                                f"[yellow]RECORDING[/yellow]  "
                                f"[dim]silence {silence_chunks}/{max_silence_chunks}[/dim]  "
                                f"{elapsed:.1f}s"
                            )
                        else:
                            vad_right = f"[yellow]RECORDING[/yellow]  [green]speech[/green]  {elapsed:.1f}s"

                        if silence_chunks > max_silence_chunks or len(frames) >= max_recording_chunks:
                            audio_data = b"".join(frames)
                            last_recording_summary = f"[cyan]DONE[/cyan]  {len(audio_data)} bytes  {elapsed:.1f}s"
                            is_recording = False
                            asr_status_right = "[yellow]TRANSCRIBING[/yellow]"
                            asr_completed = 0
                            asr_queue.put(audio_data)

                    if not is_recording and last_recording_summary:
                        vad_right = last_recording_summary
                        vad_completed = 10000

                    progress.update(
                        mic_task,
                        completed=display_val,
                        right=f"{mic_state_text}  [yellow]{rms:.2f}[/yellow]",
                    )
                    progress.update(
                        wake_task,
                        completed=wake_level,
                        right=wake_state_text,
                    )
                    progress.update(
                        vad_task,
                        completed=vad_completed,
                        right=vad_right,
                    )
                    progress.update(
                        asr_task,
                        completed=asr_completed,
                        right=asr_status_right,
                    )

    except KeyboardInterrupt:
        console.print("\n[bold red]Test stopped by user.[/bold red]")
    except Exception as e:
        console.print(f"\n[bold red]Error running mic test: {e}[/bold red]")


if __name__ == "__main__":
    main()
