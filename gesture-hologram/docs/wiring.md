# Wiring (Task 2 — do this with USB unplugged)

```
ESP32 GPIO18 ──[ 220 Ω ]──►|── GND
                          LED
                  (long leg / anode toward the resistor)
```

| Part            | Connection                                                         |
|-----------------|--------------------------------------------------------------------|
| ESP32 `GPIO18`  | one end of the 220 Ω resistor (pin is set by `LED_PIN` in the sketch) |
| 220 Ω resistor  | other end to the LED **anode** (longer leg)                        |
| LED cathode     | ESP32 `GND` (shorter leg, flat side of the lens)                    |

* GPIO output is 3.3 V; 220 Ω gives roughly 5–6 mA — comfortably within the ESP32 pin limit.
* If you wire the LED to 3.3 V instead (active-low), set `LED_ACTIVE_HIGH = false` in the sketch.
* Do **not** drive a fan or any motor from a GPIO pin. Use a transistor/MOSFET driver (with a flyback
  diode for motors) and a suitable supply when you add the optional fan.
* Use a USB cable that carries data, not a charge-only cable.

## Flashing (Task 3)

1. Arduino IDE → Boards Manager → install **esp32 by Espressif Systems**.
2. Board: *ESP32 Dev Module* (or your exact DevKit). Port: the new COM / `/dev/tty*` device.
3. Open `firmware/esp32/esp32.ino`, **Upload**. (If upload stalls, hold the **BOOT** button while it connects.)
4. Open Serial Monitor @ 115 200, line ending *Newline*, and type `PING` → `PONG`, `LED_ON` → LED lights,
   and after 5 s without further input the firmware turns it off again (`EVT:FAILSAFE_LED_OFF`).
   Close the Serial Monitor before starting the Python app — only one program can hold the port.
