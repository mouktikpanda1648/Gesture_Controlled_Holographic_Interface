"""LED bridges: the real ESP32 (via the user's ESP32Controller) and a simulator."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from .config import Settings
from .esp32_serial import ESP32Controller

log = logging.getLogger("hologram.hardware")
Emit = Callable[[str, str], None]  # (level, message)


class LedBridge:
    """Async facade over an LED controller."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def set_led(self, on: bool) -> bool: ...
    def snapshot(self) -> dict: ...


class SerialLedBridge(LedBridge):
    """Owns an ESP32Controller; connects, resyncs and reconnects in the background.

    All blocking serial work runs on one dedicated thread so the event loop (and
    therefore the UI stream) is never stalled by a slow USB transaction.
    """

    MAX_RESYNC_FAILURES = 3

    def __init__(self, settings: Settings, emit: Emit) -> None:
        self._s = settings
        self._emit = emit
        self._exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="esp32-io")
        self._ctrl: Optional[ESP32Controller] = None
        self._status = "disconnected"
        self._firmware: Optional[str] = None
        self._pending = False
        self._failures = 0
        self._task: Optional[asyncio.Task] = None

    # -- lifecycle ----------------------------------------------------------
    async def start(self) -> None:
        self._task = asyncio.create_task(self._supervise(), name="esp32-supervisor")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        ctrl, self._ctrl = self._ctrl, None
        if ctrl is not None:
            await self._run(ctrl.disconnect)  # sends LED_OFF, closes the port
        self._exec.shutdown(wait=False)
        self._status = "disconnected"

    # -- public API -----------------------------------------------------------
    async def set_led(self, on: bool) -> bool:
        ctrl = self._ctrl
        if ctrl is None or not ctrl.is_connected:
            self._emit("warn", "ESP32 not connected — command ignored")
            return False
        self._pending = True
        try:
            ok = await self._run(ctrl.set_led, on)
        finally:
            self._pending = False
        if not ok:
            self._failures += 1
            self._emit("error", f"LED_{'ON' if on else 'OFF'} was not confirmed by the ESP32")
        else:
            self._failures = 0
        return ok

    def snapshot(self) -> dict:
        ctrl = self._ctrl
        led = "unknown"
        if ctrl is not None and ctrl.led_is_on is not None:
            led = "on" if ctrl.led_is_on else "off"
        status = self._status
        if status == "connected" and self._failures:
            status = "degraded"
        return {
            "status": status,
            "port": ctrl.port if ctrl else (self._s.serial_port or None),
            "firmware": self._firmware,
            "led": led,
            "pending": self._pending,
            "simulated": False,
        }

    # -- internals -------------------------------------------------------------
    def _run(self, fn, *args):
        return asyncio.get_running_loop().run_in_executor(self._exec, fn, *args)

    def _connect_blocking(self) -> tuple[Optional[ESP32Controller], Optional[str]]:
        ctrl = ESP32Controller(port=self._s.serial_port, baudrate=self._s.baudrate)
        if not ctrl.connect():
            return None, None
        reply = ctrl.get_version() or ""
        return ctrl, reply.partition("FW=")[2] or None

    async def _supervise(self) -> None:
        backoff = 2.0
        while True:
            try:
                if self._ctrl is None:
                    self._status = "connecting"
                    ctrl, firmware = await self._run(self._connect_blocking)
                    if ctrl is None:
                        self._status = "disconnected"
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 15.0)
                        continue
                    self._ctrl, self._firmware, self._failures = ctrl, firmware, 0
                    self._status, backoff = "connected", 2.0
                    self._emit("info", f"ESP32 connected on {ctrl.port} (FW {firmware or '?'})")
                    continue

                await asyncio.sleep(2.0)
                if self._pending:
                    continue
                ctrl = self._ctrl
                # Unknown LED state (after a timeout or failsafe): re-read it.
                if ctrl.led_is_on is None or self._failures:
                    reply = await self._run(ctrl.get_status)
                    self._failures = self._failures + 1 if reply is None else 0
                    if self._failures >= self.MAX_RESYNC_FAILURES:
                        self._emit("error", "ESP32 stopped responding — reconnecting")
                        self._ctrl = None
                        self._status = "disconnected"
                        await self._run(ctrl.disconnect)
            except asyncio.CancelledError:
                raise
            except Exception:  # keep the supervisor alive no matter what
                log.exception("ESP32 supervisor error")
                await asyncio.sleep(backoff)


class SimulatedLedBridge(LedBridge):
    """Stand-in used with --simulate-esp32 for UI development without hardware."""

    def __init__(self, emit: Emit) -> None:
        self._emit = emit
        self._on = False

    async def start(self) -> None:
        self._emit("info", "Simulated ESP32 ready (no hardware)")

    async def stop(self) -> None:
        self._on = False

    async def set_led(self, on: bool) -> bool:
        await asyncio.sleep(0.05)
        self._on = on
        return True

    def snapshot(self) -> dict:
        return {
            "status": "connected",
            "port": "SIMULATED",
            "firmware": "sim",
            "led": "on" if self._on else "off",
            "pending": False,
            "simulated": True,
        }
