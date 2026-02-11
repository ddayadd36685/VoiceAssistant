import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from .state_machine import VoiceAssistant
from .logger import get_logger

logger = get_logger("Server")

app = FastAPI(title="Voice Assistant Server")

assistant: Optional[VoiceAssistant] = None
active_websockets: List[WebSocket] = []
event_queue: Optional[asyncio.Queue] = None
event_loop: Optional[asyncio.AbstractEventLoop] = None
event_task: Optional[asyncio.Task] = None

class CommandRequest(BaseModel):
    type: str
    payload: Dict[str, Any] = {}

class CommandResponse(BaseModel):
    accepted: bool
    id: str

@app.on_event("startup")
async def startup_event():
    global assistant, event_queue, event_loop, event_task
    logger.info("Starting Voice Assistant Server...")
    event_loop = asyncio.get_running_loop()
    event_queue = asyncio.Queue()

    async def event_pump():
        while True:
            msg = await event_queue.get()
            await broadcast_event(msg)

    event_task = asyncio.create_task(event_pump())

    def event_handler(event_type: str, data: Dict[str, Any]):
        msg = {"type": event_type, "ts": time.time(), "data": data}
        if event_loop is None or event_queue is None:
            return
        event_loop.call_soon_threadsafe(event_queue.put_nowait, msg)

    assistant = VoiceAssistant(on_event=event_handler)
    assistant.start()

@app.on_event("shutdown")
async def shutdown_event():
    global assistant, event_task
    if assistant:
        assistant.stop()
        assistant = None
    if event_task:
        event_task.cancel()
        event_task = None

async def broadcast_event(message: Dict[str, Any]):
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)

@app.get("/v1/health")
async def health():
    return {"ok": True, "version": "0.1.0"}

@app.get("/v1/status")
async def get_status():
    if not assistant:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
    
    return {
        "state": assistant.state.name,
        "run_mode": assistant.run_mode.name,
        "last_asr_text": assistant.last_asr_text,
        "last_intent": assistant.last_intent,
        "last_action_result": assistant.last_action_result
    }

@app.post("/v1/command", response_model=CommandResponse)
async def post_command(cmd: CommandRequest):
    if not assistant:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
    
    cmd_id = str(uuid.uuid4())
    cmd_type = cmd.type.upper()
    
    logger.info(f"Received command: {cmd_type}")
    
    if cmd_type == "PAUSE":
        assistant.pause()
    elif cmd_type == "RESUME":
        assistant.resume()
    elif cmd_type == "RELOAD_CONFIG":
        # TODO: Implement reload in state machine modules
        pass
    else:
        return CommandResponse(accepted=False, id=cmd_id)
        
    return CommandResponse(accepted=True, id=cmd_id)

@app.websocket("/v1/events")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        # Send initial status
        if assistant:
             await websocket.send_json({
                 "type": "initial_state",
                 "data": {
                    "state": assistant.state.name,
                    "run_mode": assistant.run_mode.name
                 }
             })
        while True:
            # We don't expect client to send much, but keep connection open
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
