"""Command-line entry point:  python -m backend [options]"""

from __future__ import annotations

import argparse
import logging
import threading
import webbrowser
from pathlib import Path

from aiohttp import web

from .config import Settings
from .server import create_app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m backend", description="Gesture-controlled holographic interface")
    p.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1, local only)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--camera", type=int, default=0, dest="camera_index", help="webcam index")
    p.add_argument("--serial-port", default=None, help="ESP32 port, e.g. COM3 or /dev/ttyUSB0 (default: auto)")
    p.add_argument("--baud", type=int, default=115200, dest="baudrate")
    p.add_argument("--no-mirror", action="store_true", help="do not mirror the camera image")
    p.add_argument("--model", type=Path, default=None, help="path to hand_landmarker.task")
    p.add_argument("--open", action="store_true", dest="open_browser", help="open the UI in the default browser")
    p.add_argument("--simulate-camera", action="store_true", help="no webcam; inject gestures with keys 1/2/3")
    p.add_argument("--simulate-esp32", action="store_true", help="no ESP32; use a simulated LED")
    p.add_argument("--simulate", action="store_true", help="shortcut for both --simulate-* flags")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    a = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    kwargs = dict(
        host=a.host, port=a.port, camera_index=a.camera_index, serial_port=a.serial_port,
        baudrate=a.baudrate, mirror=not a.no_mirror, open_browser=a.open_browser,
        simulate_camera=a.simulate or a.simulate_camera,
        simulate_esp32=a.simulate or a.simulate_esp32,
    )
    if a.model:
        kwargs["model_path"] = a.model
    settings = Settings(**kwargs)

    url = f"http://{'localhost' if a.host in ('127.0.0.1', '0.0.0.0') else a.host}:{a.port}/"
    logging.getLogger("hologram").info("UI: %s   (H = hologram view, F = fullscreen)", url)
    if settings.open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    web.run_app(create_app(settings), host=a.host, port=a.port, print=None, handle_signals=True)


if __name__ == "__main__":
    main()
