"""Local HUD server: serves the static frontend and pushes voice-loop events
to it over a WebSocket. Runs in a background thread with its own event loop
so the fully synchronous main.py voice loop doesn't need to become async."""

import asyncio
import json
import queue
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from janet import config
from janet.rag.inbox import SUPPORTED_SUFFIXES

_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    def register(self, ws: WebSocket) -> None:
        self._clients.add(ws)

    def unregister(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, event: dict) -> None:
        dead = set()
        for ws in self._clients:
            try:
                await ws.send_json(event)
            except Exception:
                dead.add(ws)
        self._clients -= dead


def _build_app(event_queue: queue.Queue, command_queue: queue.Queue) -> FastAPI:
    app = FastAPI()
    hub = Hub()

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")

    @app.post("/upload")
    async def upload(request: Request, name: str) -> JSONResponse:
        """Saves a file dropped onto the HUD into INBOX_DIR, where rag.inbox's
        watcher picks it up. The raw file is the request body (no multipart),
        so this needs no extra dependency."""
        if not config.RAG_ENABLED:
            return JSONResponse({"error": "RAG is disabled (RAG_ENABLED=false)."}, status_code=400)
        filename = Path(name).name  # strip any directory parts a client might send
        if Path(filename).suffix.lower() not in SUPPORTED_SUFFIXES:
            return JSONResponse({"error": f"Unsupported file type: {filename}"}, status_code=400)
        body = await request.body()
        if len(body) > config.UPLOAD_MAX_MB * 1024 * 1024:
            return JSONResponse({"error": f"File is larger than {config.UPLOAD_MAX_MB} MB."}, status_code=413)
        inbox = Path(config.INBOX_DIR)
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / filename).write_bytes(body)
        return JSONResponse({"ok": True, "name": filename})

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        hub.register(ws)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    command_queue.put(json.loads(raw))
                except ValueError:
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            hub.unregister(ws)

    @app.on_event("startup")
    async def _start_event_pump() -> None:
        loop = asyncio.get_running_loop()

        def pump_from_thread() -> None:
            # A plain daemon thread (not asyncio's default ThreadPoolExecutor)
            # is deliberate: executor worker threads are joined by an atexit
            # hook regardless of daemon status, so a permanently-blocked
            # event_queue.get() there would hang the whole interpreter at
            # shutdown once the voice loop stops feeding it. A raw daemon
            # thread is simply abandoned when the process exits.
            while True:
                event = event_queue.get()
                asyncio.run_coroutine_threadsafe(hub.broadcast(event), loop)

        threading.Thread(target=pump_from_thread, daemon=True).start()

    return app


def start_ui_server(event_queue: queue.Queue, command_queue: queue.Queue, port: int) -> None:
    """Blocking call — run this as the target of a background thread."""
    app = _build_app(event_queue, command_queue)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
