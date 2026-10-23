# Holo-Link — Gesture-Controlled Holographic-Style Interface

Hand gesture → laptop recognition → ESP32 command → physical LED, shown through a transparent
pyramid (Pepper's-ghost illusion). Built for the IIIT Bhubaneswar EEE exhibition from the
*Beginner Build Guide*.

| Gesture     | Action                                            |
|-------------|---------------------------------------------------|
| ☝ **Point**      | highlights **LIGHT** (stays selected for 5 s)     |
| 👍 **Thumbs up** | turns the LED **ON** (hold ~0.6 s, LIGHT selected) |
| ✋ **Open palm** | turns the LED **OFF** (hold ~0.5 s, always works)  |

`FAN` and `TEMP` appear in the menu as *Not installed*, matching the "basic version only needs LIGHT"
scope. Gesture mapping lives in `backend/interface.py`; thresholds in `backend/gestures.py`.

```
 webcam ─► OpenCV ─► MediaPipe Hand Landmarker ─► gesture classifier ─► debounce ─► interface FSM
                                                                                       │
 browser UI (HTML/CSS/JS canvas) ◄──── WebSocket (30 Hz state) ────── aiohttp ◄────────┤
                                                                                       ▼
                                               ESP32Controller (PySerial, heartbeat) ─► ESP32 ─► LED
```

## Repository layout

```
firmware/esp32/esp32.ino     ESP32 firmware (serial command protocol, failsafe)
backend/
  esp32_serial.py            ESP32Controller (PySerial, heartbeat, reconnect-safe)
  hardware.py                async bridge: background connect / resync / reconnect, simulator
  tracker.py                 webcam thread + MediaPipe Tasks Hand Landmarker
  gestures.py                landmark → gesture classifier, debouncer, hold-to-confirm
  interface.py               menu focus + gesture → LED action rules
  server.py / __main__.py    aiohttp server, WebSocket stream, CLI
  preview.py                 camera + landmark test window (Task 4)
frontend/                    dependency-free ES-module UI (works fully offline)
scripts/                     download_model.py, pyramid_template.py
tests/                       pytest suite (classifier, FSM, server, serial bridge on a pty)
docs/                        wiring, protocol, pyramid & display setup
```

## Quick start

Python 3.10+ and a USB webcam. Build order follows the guide: LED → camera → serial → UI → pyramid.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/download_model.py     # one-off, ~7 MB hand model (needs internet)
```

1. **Wire and flash the ESP32** — [docs/wiring.md](docs/wiring.md). Close the Arduino Serial Monitor afterwards.
2. **Check hand detection (Task 4):** `python -m backend.preview` — you should see the skeleton and the
   gesture label. Try your real lighting here.
3. **Run everything:**
   ```bash
   python -m backend --open                       # auto-detects camera 0 and the ESP32
   python -m backend --serial-port COM3           # or /dev/ttyUSB0, if auto-detect finds several
   ```
4. **Hologram view:** press **H** (fullscreen **F**), then follow [docs/pyramid.md](docs/pyramid.md).

No hardware yet? `python -m backend --simulate` runs the whole UI with a simulated camera and LED;
use keys **1 / 2 / 3** for point / thumbs up / open palm.

### Options

| Flag | Meaning |
|------|---------|
| `--camera N` | webcam index (default 0) |
| `--serial-port P` | ESP32 port (default: auto-detect) |
| `--no-mirror` | disable selfie mirroring |
| `--simulate-camera` / `--simulate-esp32` / `--simulate` | develop without that hardware |
| `--host 0.0.0.0` | allow other devices on the network (default is local only) |
| `--open`, `-v` | open the browser, verbose logging |

Keys in the UI: **H** hologram view · **F** fullscreen · **G** alignment guide · **+ −** image size ·
**[ ]** distance from centre.

## Reliability and safety design

* **Failsafe:** the firmware turns the LED off 5 s after the last `PING`; the laptop pings every
  1.5 s. A crash, unplugged cable or frozen laptop cannot leave the LED on. Exiting normally sends `LED_OFF`.
* **Self-healing:** the ESP32 link reconnects with back-off if the cable is replugged; the browser
  reconnects to the backend automatically. The UI shows *CONTROLLER NOT CONNECTED* / *BACKEND OFFLINE*.
* **No accidental triggers:** gestures must be held, fire once, and need a release before re-firing;
  single-frame classification flicker is filtered. Thumbs-up only works while LIGHT is selected;
  open palm always switches off.
* **Non-blocking:** all serial I/O runs on its own thread, so a slow USB transaction never freezes the UI.
* **Local by default:** binds to `127.0.0.1`, whitelists commands, rejects cross-origin WebSockets and
  ships a strict Content-Security-Policy. Low-voltage USB/3.3 V only — never connect mains to the breadboard.

## Tests

```bash
pip install -r requirements-dev.txt
pytest          # classifier, debouncer, FSM, server (simulated), and the serial bridge against a firmware model
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| *Hand model unavailable* | run `python scripts/download_model.py` once with internet, or place `hand_landmarker.task` in `backend/models/` |
| *Cannot open camera* | try `--camera 1`; close other apps using the webcam; on Windows allow camera access |
| ESP32 *disconnected* | data-capable cable? Serial Monitor closed? Try `--serial-port`; install the CP210x/CH340 driver |
| Gesture misread | run `python -m backend.preview`, improve front lighting, tune thresholds at the top of `gestures.py` |
| Floating image misaligned | [docs/pyramid.md](docs/pyramid.md); use the **G** guide and the size/distance controls |

## Extending (Fan, Temp, OLED)

Add the command to the firmware table (`COMMANDS[]`), to `VALID_COMMANDS` / `_matches_response` in
`esp32_serial.py`, then enable the item in `DEFAULT_ITEMS` (`interface.py`). Drive a fan through a
transistor/MOSFET module — never straight from a GPIO pin.

## Status

This repository implements the design in the guide. The classifier, state machine, server, UI and serial
bridge are covered by automated tests (the serial tests use a firmware model on a pseudo-terminal), but it has **not yet been
run against a physical webcam, ESP32 or pyramid**. Expect to tune gesture thresholds and the pyramid
alignment on your own hardware.
