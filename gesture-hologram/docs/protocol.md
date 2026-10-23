# Serial & WebSocket protocols

## Laptop ⇄ ESP32 (USB serial, 115 200 baud, `\n`-terminated ASCII)

Implemented by `firmware/esp32/esp32.ino` and `backend/esp32_serial.py` (`ESP32Controller`).

| Command   | Reply                               | Notes                                   |
|-----------|-------------------------------------|-----------------------------------------|
| `PING`    | `PONG`                              | Heartbeat; resets the 5 s failsafe timer |
| `LED_ON`  | `ACK:LED_ON`                        |                                         |
| `LED_OFF` | `ACK:LED_OFF`                       |                                         |
| `STATUS`  | `STATUS:LED_ON` / `STATUS:LED_OFF`  |                                         |
| `VERSION` | `VERSION:FW=<x.y>`                  |                                         |

Unsolicited lines: `READY` (boot), `EVT:FAILSAFE_LED_OFF` (no heartbeat for 5 s while the LED was on).
Errors: `ERR:UNKNOWN_COMMAND`, `ERR:INVALID_CHAR`, `ERR:LINE_TOO_LONG`, `ERR:TIMEOUT`.

The controller pings every 1.5 s, so the firmware failsafe only fires if the laptop, cable or backend
fails — the LED can never be left on by a crashed program.

## Browser ⇄ backend (`ws://localhost:8765/ws`, JSON text frames)

Server → client

| `type`  | Payload                                                                                          |
|---------|--------------------------------------------------------------------------------------------------|
| `hello` | `version`, `simulate`, `inject`, `log[]` — sent once on connect                                  |
| `state` | `camera{status,detail,fps}`, `hand{present,landmarks[21][x,y],gesture,progress}`, `ui{focus,items[]}`, `link{status,port,firmware,led,pending,simulated}` — up to 30 Hz |
| `log`   | `level` (`info`/`warn`/`error`), `msg`, `t` (epoch seconds)                                      |

Client → server

| `type`    | Fields                          | Effect                                                         |
|-----------|---------------------------------|----------------------------------------------------------------|
| `command` | `cmd`: `LED_ON` \| `LED_OFF`    | Manual override (whitelisted; anything else is ignored)         |
| `inject`  | `gesture`: `POINT` \| `THUMBS_UP` \| `OPEN_PALM` \| `NONE` | Only honoured with `--simulate-camera`; used by keys 1/2/3 |

Cross-origin WebSocket connections are refused, so a random web page cannot toggle the LED.
