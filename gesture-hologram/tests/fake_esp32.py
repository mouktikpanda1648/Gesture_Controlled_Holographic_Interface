"""A Python model of firmware/esp32/esp32.ino on a pseudo-terminal (same protocol + failsafe)."""
import os
import threading
import time


class FakeESP32:
    FAILSAFE_S = 5.0

    def __init__(self, failsafe_s=FAILSAFE_S):
        self.master, slave = os.openpty()
        self.path = os.ttyname(slave)
        self._slave = slave  # keep open so the pty survives reconnects
        self.failsafe_s = failsafe_s
        self.led = False
        self.last_beat = time.monotonic()
        self.log: list[str] = []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._t.start()
        return self

    def stop(self):
        self._stop.set()
        self._t.join(timeout=1)
        os.close(self.master)
        os.close(self._slave)

    def _send(self, line):
        os.write(self.master, (line + "\r\n").encode())

    def _run(self):
        import select
        buf = b""
        while not self._stop.is_set():
            if self.led and time.monotonic() - self.last_beat >= self.failsafe_s:
                self.led = False
                self._send("EVT:FAILSAFE_LED_OFF")
            r, _, _ = select.select([self.master], [], [], 0.02)
            if not r:
                continue
            try:
                buf += os.read(self.master, 256)
            except OSError:
                return
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle(line.strip().decode(errors="replace").upper())

    def _handle(self, cmd):
        if not cmd:
            return
        self.log.append(cmd)
        if cmd == "PING":
            self.last_beat = time.monotonic()
            self._send("PONG")
        elif cmd == "LED_ON":
            if not self.led:
                self.led = True
                self.last_beat = time.monotonic()
            self._send("ACK:LED_ON")
        elif cmd == "LED_OFF":
            self.led = False
            self._send("ACK:LED_OFF")
        elif cmd == "STATUS":
            self._send("STATUS:LED_ON" if self.led else "STATUS:LED_OFF")
        elif cmd == "VERSION":
            self._send("VERSION:FW=1.0")
        else:
            self._send("ERR:UNKNOWN_COMMAND")
