"""aiohttp application: serves the UI and streams state over a WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web

from . import __version__
from .config import FRONTEND_DIR, Settings
from .gestures import DebounceResult, Gesture, GestureDebouncer
from .hardware import LedBridge, SerialLedBridge, SimulatedLedBridge
from .interface import InterfaceModel, Notice, SetLed
from .tracker import CameraTracker, Observation

log = logging.getLogger("hologram.server")
HOLOGRAM_KEY: web.AppKey["HologramApp"] = web.AppKey("hologram")

BROADCAST_INTERVAL_S = 1 / 30
INJECT_TTL_S = 3.0


class HologramApp:
    """Glue: tracker -> debouncer -> interface model -> LED bridge -> UI clients."""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.clients: set[web.WebSocketResponse] = set()
        self.logbuf: deque[dict] = deque(maxlen=60)

        self.debouncer = GestureDebouncer(settings.hold_times)
        self.model = InterfaceModel(settings.focus_timeout_s)
        self.bridge: LedBridge = (
            SimulatedLedBridge(self.emit) if settings.simulate_esp32 else SerialLedBridge(settings, self.emit)
        )

        self.camera = {"status": "off" if settings.simulate_camera else "starting", "detail": "", "fps": 0.0}
        self.last_obs: Observation | None = None
        self._result = DebounceResult(Gesture.NONE, 0.0, None)
        self._override: tuple[Gesture, float] | None = None

        self._queue: asyncio.Queue[Observation] = asyncio.Queue(maxsize=2)
        self._led_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []
        self._tracker: CameraTracker | None = None
        self._last_broadcast = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None

    # ---- lifecycle -----------------------------------------------------------
    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        await self.bridge.start()
        if not self.s.simulate_camera:
            self._tracker = CameraTracker(self.s, self._from_thread_obs, self._from_thread_status)
            self._tracker.start()
        else:
            self.emit("info", "Simulated camera — use keys 1 / 2 / 3 in the UI to inject gestures")
        self._tasks = [
            asyncio.create_task(self._pipeline(), name="pipeline"),
            asyncio.create_task(self._ticker(), name="ticker"),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._tracker:
            await asyncio.to_thread(self._tracker.stop)
        await self.bridge.stop()
        for ws in list(self.clients):
            await ws.close(code=1001, message=b"server shutdown")

    # ---- thread -> loop bridges ---------------------------------------------
    def _from_thread_obs(self, obs: Observation) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._enqueue, obs)

    def _enqueue(self, obs: Observation) -> None:
        if self._queue.full():
            self._queue.get_nowait()  # drop the stale frame, keep latency low
        self._queue.put_nowait(obs)

    def _from_thread_status(self, status: str, detail: str) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._set_camera_status, status, detail)

    def _set_camera_status(self, status: str, detail: str) -> None:
        changed = status != self.camera["status"]
        self.camera.update(status=status, detail=detail)
        if changed:
            self.emit("info" if status == "ok" else "warn", f"Camera: {status} — {detail}")

    # ---- events / logging ----------------------------------------------------
    def emit(self, level: str, message: str) -> None:
        getattr(log, {"warn": "warning"}.get(level, level), log.info)(message)
        entry = {"type": "log", "level": level, "msg": message, "t": time.time()}
        self.logbuf.append(entry)
        self._send_all(entry)

    # ---- processing ----------------------------------------------------------
    async def _pipeline(self) -> None:
        while True:
            obs = await self._queue.get()
            self.last_obs = obs
            self.camera["fps"] = obs.fps
            await self._process(obs.gesture, obs.t)
            self._broadcast_state()

    async def _ticker(self) -> None:
        """Keeps simulated input, focus timeouts and status fresh even without frames."""
        while True:
            await asyncio.sleep(0.05)
            now = time.monotonic()
            idle = self.last_obs is None or now - self.last_obs.t > 0.2
            if self.s.simulate_camera or idle:
                gesture = Gesture.NONE
                if self.s.simulate_camera:
                    self.last_obs = Observation(now, Gesture.NONE, None, 20.0)
                    self.camera.update(status="off", fps=20.0, detail="simulated")
                await self._process(gesture, now)
                self._broadcast_state()

    async def _process(self, raw: Gesture, now: float) -> None:
        if self._override:
            gesture, until = self._override
            if now < until:
                raw = gesture
            else:
                self._override = None
        self._result = self.debouncer.update(raw, now)
        for effect in self.model.update(self._result, now):
            if isinstance(effect, SetLed):
                asyncio.create_task(self._apply_led(effect.on, effect.source))
            elif isinstance(effect, Notice):
                self.emit("info", effect.message)

    async def _apply_led(self, on: bool, source: str) -> None:
        async with self._led_lock:
            ok = await self.bridge.set_led(on)
        if ok:
            self.emit("info", f"LED {'ON' if on else 'OFF'} ({source})")
        self._broadcast_state(force=True)

    # ---- client messages -------------------------------------------------------
    async def handle_message(self, data: dict) -> None:
        kind = data.get("type")
        if kind == "inject" and self.s.allow_inject:
            name = str(data.get("gesture", "NONE"))
            try:
                gesture = Gesture(name)
            except ValueError:
                return
            if gesture == Gesture.NONE:
                self._override = None
            else:
                self._override = (gesture, time.monotonic() + INJECT_TTL_S)
        elif kind == "command":
            cmd = data.get("cmd")
            if cmd in ("LED_ON", "LED_OFF"):
                asyncio.create_task(self._apply_led(cmd == "LED_ON", "manual"))

    # ---- broadcasting ----------------------------------------------------------
    def snapshot(self) -> dict:
        obs = self.last_obs
        landmarks = None
        if obs and obs.landmarks and time.monotonic() - obs.t < 0.3:
            landmarks = [[round(x, 3), round(y, 3)] for x, y, _ in obs.landmarks]
        r = self._result
        return {
            "type": "state",
            "camera": dict(self.camera),
            "hand": {
                "present": r.active != Gesture.NONE or landmarks is not None,
                "landmarks": landmarks,
                "gesture": r.active.value,
                "progress": round(r.progress, 3),
            },
            "ui": self.model.snapshot(),
            "link": self.bridge.snapshot(),
        }

    def hello(self) -> dict:
        return {
            "type": "hello",
            "version": __version__,
            "simulate": self.s.simulate_camera or self.s.simulate_esp32,
            "inject": self.s.allow_inject,
            "log": list(self.logbuf),
        }

    def _send_all(self, payload: dict) -> None:
        if not self.clients:
            return
        text = json.dumps(payload, separators=(",", ":"))
        for ws in list(self.clients):
            if not ws.closed:
                asyncio.create_task(self._safe_send(ws, text))

    @staticmethod
    async def _safe_send(ws: web.WebSocketResponse, text: str) -> None:
        try:
            await ws.send_str(text)
        except (ConnectionResetError, RuntimeError):
            pass

    def _broadcast_state(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_broadcast < BROADCAST_INTERVAL_S:
            return
        self._last_broadcast = now
        self._send_all(self.snapshot())


# ---------------------------------------------------------------------------
# aiohttp wiring
# ---------------------------------------------------------------------------

def _origin_allowed(request: web.Request) -> bool:
    """Reject cross-site WebSocket connections (a webpage must not toggle the LED)."""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    return urlsplit(origin).netloc == request.host


async def ws_handler(request: web.Request) -> web.StreamResponse:
    if not _origin_allowed(request):
        raise web.HTTPForbidden(text="cross-origin WebSocket refused")
    app: HologramApp = request.app[HOLOGRAM_KEY]
    ws = web.WebSocketResponse(heartbeat=20.0, max_msg_size=4096)
    await ws.prepare(request)
    app.clients.add(ws)
    await ws.send_str(json.dumps(app.hello()))
    await ws.send_str(json.dumps(app.snapshot()))
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    await app.handle_message(data)
    finally:
        app.clients.discard(ws)
    return ws


async def health(request: web.Request) -> web.Response:
    app: HologramApp = request.app[HOLOGRAM_KEY]
    return web.json_response({"ok": True, "version": __version__, "state": app.snapshot()})


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(FRONTEND_DIR / "index.html")


@web.middleware
async def security_headers(request: web.Request, handler):
    response = await handler(request)
    response.headers.setdefault("Cache-Control", "no-cache")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data:; style-src 'self'",
    )
    return response


def create_app(settings: Settings) -> web.Application:
    app = web.Application(middlewares=[security_headers])
    holo = HologramApp(settings)
    app[HOLOGRAM_KEY] = holo

    async def on_startup(_: web.Application) -> None:
        await holo.start()

    async def on_cleanup(_: web.Application) -> None:
        await holo.stop()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/api/health", health)
    app.router.add_static("/css", FRONTEND_DIR / "css")
    app.router.add_static("/js", FRONTEND_DIR / "js")
    return app
