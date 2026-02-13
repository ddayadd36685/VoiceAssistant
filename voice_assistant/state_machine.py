import time
import threading
from enum import Enum, auto
from typing import Callable, Optional, Dict, Any

from .logger import get_logger, console
from .audio_stream import MicrophoneStream
from .wakeword import WakeWordDetector
from .vad_recorder import VadRecorder
from .asr import ASR
from .parser import Parser
from .mcp_client import MCPClient, ensure_mcp_config_files

import os
try:
    import os
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
    import pygame
except ImportError:
    pygame = None

class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    EXECUTING = auto()

class RunMode(Enum):
    RUNNING = auto()
    PAUSED = auto()

class VoiceAssistant:
    def __init__(self, on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None):
        self.logger = get_logger("VoiceAssistant")
        self.state = State.IDLE
        self.run_mode = RunMode.RUNNING
        self.running = False
        self.on_event = on_event
        
        ensure_mcp_config_files()

        # Initialize modules
        self.wakeword = WakeWordDetector()
        self.vad = VadRecorder()
        self.asr = ASR()
        self.parser = Parser()
        self.mcp = MCPClient()
        
        # Init sound
        self.sound_start = None
        self.sound_stop = None
        if pygame:
            try:
                pygame.mixer.init()
                root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                start_path = os.path.join(root, "sound", "start.wav")
                stop_path = os.path.join(root, "sound", "stop.mp3")
                
                if os.path.exists(start_path):
                    self.sound_start = pygame.mixer.Sound(start_path)
                if os.path.exists(stop_path):
                    self.sound_stop = pygame.mixer.Sound(stop_path)
            except Exception as e:
                self.logger.warning(f"Failed to init pygame sound: {e}")

        # Runtime data
        self.last_asr_text = ""
        self.last_intent = {}
        self.last_action_result = {}

    def _play_prompt_tone(self, kind: str) -> None:
        sound = None
        if kind == "start":
            sound = self.sound_start
        elif kind == "stop":
            sound = self.sound_stop
            
        if sound:
            try:
                sound.play()
                # Wait for sound to finish to avoid recording it
                # For start sound, we want to wait. For stop sound, maybe not strictly necessary but good for UX.
                dur = sound.get_length()
                if dur > 0:
                    time.sleep(dur + 0.1)
            except Exception as e:
                self.logger.debug(f"Pygame play failed: {e}")

    def _emit(self, event_type: str, data: Dict[str, Any] = None):
        if data is None:
            data = {}
        if self.on_event:
            try:
                self.on_event(event_type, data)
            except Exception as e:
                self.logger.error(f"Event callback failed: {e}")

    def start(self):
        """Start the loop in a background thread."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2)

    def pause(self):
        self.run_mode = RunMode.PAUSED
        self._emit("run_mode_changed", {"mode": "PAUSED"})
        self.logger.info("Voice Assistant paused.")

    def resume(self):
        self.run_mode = RunMode.RUNNING
        self._emit("run_mode_changed", {"mode": "RUNNING"})
        self.logger.info("Voice Assistant resumed.")

    def _set_state(self, new_state: State):
        old_state = self.state
        self.state = new_state
        self._emit("state_changed", {"from": old_state.name, "to": new_state.name})

    def _run_loop(self):
        self.logger.info("Voice Assistant loop starting...")
        self._emit("loop_started")
        
        try:
            with MicrophoneStream() as stream:
                self.logger.info("Microphone initialized.")
                
                while self.running:
                    try:
                        if self.run_mode == RunMode.PAUSED:
                            time.sleep(0.5)
                            continue

                        if self.state == State.IDLE:
                            # Read small chunk for wake word detection
                            chunk = stream.read()
                            
                            # Process returns keyword string if detected, else None
                            keyword = self.wakeword.process(chunk)
                            if keyword:
                                self.logger.info(f"Wake Word Detected: {keyword}")
                                self._emit("wakeword_detected", {"keyword": keyword})
                                self._set_state(State.LISTENING)
                                
                        elif self.state == State.LISTENING:
                            # Capture audio until silence
                            self._play_prompt_tone("start")
                            try:
                                stream.queue.clear()
                            except Exception:
                                pass
                            self._emit("recording_started")
                            audio_data = self.vad.capture(stream)
                            self._play_prompt_tone("stop")
                            self.logger.info(f"Recorded {len(audio_data)} bytes.")
                            self._emit("recording_stopped", {"bytes": len(audio_data)})
                            
                            self._set_state(State.THINKING)
                            self.audio_buffer = audio_data
                            
                        elif self.state == State.THINKING:
                            text = self.asr.transcribe(self.audio_buffer)
                            self.last_asr_text = text
                            self._emit("asr_result", {"text": text})

                            parsed = self.parser.parse(text)
                            self.current_intent = parsed
                            self.last_intent = parsed
                            self._emit("intent_parsed", parsed)
                            
                            self._set_state(State.EXECUTING)
                            
                        elif self.state == State.EXECUTING:
                            actions = self.current_intent.get("actions", [])
                            reply = self.current_intent.get("reply", "")
                            
                            # Log and emit start
                            self._emit("action_started", {"actions": actions, "reply": reply})

                            results = []
                            overall_success = True
                            
                            for action in actions:
                                intent = action.get("intent", "unknown")
                                target = action.get("target", "")
                                
                                if intent in ("unknown", "chat"):
                                    continue
                                
                                success = self.mcp.execute(intent, target)
                                if not success:
                                    overall_success = False
                                    results.append(f"操作失败: {target}")
                                else:
                                    results.append(f"已执行: {target}")

                            # If no system actions were performed, use reply as result message
                            if not results:
                                result_msg = reply
                            else:
                                # Combine system results
                                action_summary = "；".join(results)
                                if reply:
                                    result_msg = f"{reply} ({action_summary})"
                                else:
                                    result_msg = action_summary
                            
                            self.last_action_result = {"success": overall_success, "message": result_msg}
                            self._emit("action_finished", self.last_action_result)
                            
                            self.logger.info(f"Execution done. Reply: {result_msg}")
                            self._set_state(State.IDLE)
                            
                            # Cooldown to avoid self-triggering from system sounds or echoes
                            time.sleep(1) 
                            # Clear buffer
                            stream.queue.clear() 
                            
                    except Exception as e:
                        self.logger.error(f"Error in loop: {e}", exc_info=True)
                        self._emit("error", {"message": str(e)})
                        self._set_state(State.IDLE)
                        time.sleep(1)
                        
        except Exception as e:
             self.logger.critical(f"Failed to initialize microphone: {e}")
             self._emit("fatal_error", {"message": str(e)})
