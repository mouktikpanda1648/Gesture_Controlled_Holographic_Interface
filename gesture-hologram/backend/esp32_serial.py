
import time
import threading
from typing import Optional

import serial
import serial.tools.list_ports


class ESP32Controller:
    """
    Serial controller for the ESP32 gesture-interface project.

    Compatible with the current firmware commands:
        PING, LED_ON, LED_OFF, STATUS, VERSION

    Features:
        - USB serial port discovery
        - PING/PONG connection handshake
        - Serialized request-response transactions
        - Background heartbeat
        - Asynchronous firmware event handling
        - LED state caching with invalidation
        - Bounded line buffering and timeout handling
        - Graceful shutdown
    """

    VALID_COMMANDS = frozenset({
        "PING",
        "LED_ON",
        "LED_OFF",
        "STATUS",
        "VERSION",
    })

    MAX_RX_LINE_BYTES = 128
    READ_POLL_INTERVAL = 0.10

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        timeout: float = 0.5,
        heartbeat_interval: float = 1.5,
        startup_delay: float = 1.5,
        failsafe_timeout: float = 5.0,
    ):
        if baudrate <= 0:
            raise ValueError("baudrate must be positive")

        if timeout <= 0:
            raise ValueError("timeout must be positive")

        if heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval must be positive")

        if startup_delay < 0:
            raise ValueError("startup_delay cannot be negative")

        if failsafe_timeout <= 0:
            raise ValueError("failsafe_timeout must be positive")

        # Leave a reasonable margin below the firmware failsafe.
        if heartbeat_interval + timeout >= failsafe_timeout:
            raise ValueError(
                "heartbeat_interval + timeout must be less "
                "than the firmware failsafe timeout"
            )

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.heartbeat_interval = heartbeat_interval
        self.startup_delay = startup_delay
        self.failsafe_timeout = failsafe_timeout

        self.ser: Optional[serial.Serial] = None

        # Only one thread may perform a serial transaction at a time.
        self._io_lock = threading.Lock()

        # Protect cached application state independently.
        self._state_lock = threading.Lock()

        self._stop_event = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

        self._connected = False
        self._closing = False

        self._rx_buffer = bytearray()
        self._discarding_rx_line = False

        # None means the physical LED state is unknown.
        self.led_is_on: Optional[bool] = None

        self._consecutive_heartbeat_failures = 0

    # ---------------------------------------------------------
    # Port discovery
    # ---------------------------------------------------------

    @staticmethod
    def list_serial_ports():
        """Return a snapshot of available serial ports."""
        return list(serial.tools.list_ports.comports())

    @staticmethod
    def find_esp32_port() -> Optional[str]:
        """
        Detect common USB-to-UART adapters.

        If several candidates exist, require the caller to select
        a port explicitly instead of guessing.
        """
        identifiers = (
            "CP210",
            "CH340",
            "CH9102",
            "USB Serial",
            "UART",
            "Silicon Labs",
            "FTDI",
        )

        ports = list(serial.tools.list_ports.comports())
        matches = []

        for item in ports:
            description = (
                f"{item.description or ''} "
                f"{item.manufacturer or ''}"
            ).lower()

            if any(key.lower() in description for key in identifiers):
                matches.append(item.device)

        if len(matches) == 1:
            return matches[0]

        if len(matches) > 1:
            print(
                "[ESP32] Multiple possible serial devices found:",
                ", ".join(matches),
            )
            print("[ESP32] Specify the correct port manually.")
            return None

        # A single available port is a useful fallback, but it is
        # not proof that the device is an ESP32.
        if len(ports) == 1:
            return ports[0].device

        return None

    @property
    def is_connected(self) -> bool:
        """Whether a handshake succeeded and the serial port is open."""
        return (
            self._connected
            and self.ser is not None
            and self.ser.is_open
            and not self._closing
        )

    # ---------------------------------------------------------
    # Response protocol
    # ---------------------------------------------------------

    @staticmethod
    def _matches_response(cmd: str, response: str) -> bool:
        """Check whether a line is a valid response for a command."""
        if response.startswith("ERR:"):
            return True

        if cmd == "PING":
            return response == "PONG"

        if cmd == "LED_ON":
            return response == "ACK:LED_ON"

        if cmd == "LED_OFF":
            return response == "ACK:LED_OFF"

        if cmd == "STATUS":
            return response in (
                "STATUS:LED_ON",
                "STATUS:LED_OFF",
            )

        if cmd == "VERSION":
            return (
                response.startswith("VERSION:")
                and len(response) > len("VERSION:")
            )

        return False

    def _set_led_cache(self, value: Optional[bool]) -> None:
        with self._state_lock:
            self.led_is_on = value

    def _handle_event(self, event: str) -> None:
        """
        Handle unsolicited ESP32 events.

        This function is called while the serial transaction lock
        is held. It must not initiate another serial transaction.
        """
        print(f"[ESP32] Event: {event}")

        if event == "EVT:FAILSAFE_LED_OFF":
            self._set_led_cache(False)

    def _read_line_until(self, deadline: float) -> Optional[str]:
        """
        Read one complete newline-terminated line.

        Partial data survives a read timeout and can be completed
        by subsequent reads. Returns None on deadline expiration.
        Must be called while _io_lock is held.
        """
        if self.ser is None:
            return None

        while time.monotonic() < deadline:
            if not self.ser.is_open:
                return None

            remaining = deadline - time.monotonic()

            self.ser.timeout = min(
                self.READ_POLL_INTERVAL,
                max(0.001, remaining),
            )

            chunk = self.ser.read(1)

            if not chunk:
                continue

            byte = chunk[0]

            if byte == 0x0A:  # LF terminates a line
                if self._discarding_rx_line:
                    self._discarding_rx_line = False
                    self._rx_buffer.clear()
                    return ""

                line = bytes(self._rx_buffer)
                self._rx_buffer.clear()

                # Remove any trailing CR in CRLF.
                if line.endswith(b"\r"):
                    line = line[:-1]

                return line.decode("ascii", errors="replace")

            if self._discarding_rx_line:
                continue

            # CR is ignored, matching the firmware's receiver.
            if byte == 0x0D:
                continue

            self._rx_buffer.append(byte)

            if len(self._rx_buffer) > self.MAX_RX_LINE_BYTES:
                self._rx_buffer.clear()
                self._discarding_rx_line = True
                print("[ESP32] Oversized response line discarded.")

        return None

    # ---------------------------------------------------------
    # Core serial transaction
    # ---------------------------------------------------------

    def send_command(self, cmd: str) -> Optional[str]:
        """
        Send one supported command and wait for its response.

        Returns:
            Response string on success or firmware ERR response.
            None on timeout, disconnection, or serial failure.
        """
        if not isinstance(cmd, str):
            return None

        cmd = cmd.strip().upper()

        if cmd not in self.VALID_COMMANDS:
            print(f"[ESP32] Unsupported local command: {cmd!r}")
            return None

        payload = (cmd + "\n").encode("ascii")

        with self._io_lock:
            if (self.ser is None or not self.ser.is_open or (self._closing and cmd != "LED_OFF")):
                return None

            try:
                # Each transaction has one writer and one reader.
                self.ser.write(payload)
                self.ser.flush()

                deadline = time.monotonic() + self.timeout

                while time.monotonic() < deadline:
                    response = self._read_line_until(deadline)

                    if response is None:
                        break

                    if not response:
                        continue

                    if response == "READY":
                        # Startup notification, not a command reply.
                        continue

                    if response.startswith("EVT:"):
                        self._handle_event(response)
                        continue

                    if self._matches_response(cmd, response):
                        return response

                    # Do not treat an unrelated line as success.
                    print(
                        f"[ESP32] Unexpected response while "
                        f"waiting for {cmd}: {response!r}"
                    )

                self._set_led_cache(None)
                return None

            except (serial.SerialException, OSError) as exc:
                self._set_led_cache(None)
                print(f"[ESP32] Serial communication error: {exc}")
                return None

            finally:
                if self.ser is not None:
                    self.ser.timeout = self.READ_POLL_INTERVAL

    # ---------------------------------------------------------
    # Connection and handshake
    # ---------------------------------------------------------

    def connect(self, retries: int = 5) -> bool:
        """
        Open the port and establish communication using PING/PONG.

        The firmware may reset when the USB serial port opens.
        Handshake retries allow time for startup.
        """
        if retries < 1:
            raise ValueError("retries must be at least 1")

        if self.is_connected:
            return True

        self._closing = False
        self._stop_event.clear()
        self._set_led_cache(None)

        target_port = self.port or self.find_esp32_port()

        if not target_port:
            print(
                "[ESP32] No unambiguous serial port found. "
                "Specify the port manually."
            )
            return False

        try:
            self.ser = serial.Serial(
                port=target_port,
                baudrate=self.baudrate,
                timeout=self.READ_POLL_INTERVAL,
                write_timeout=self.timeout,
                dsrdtr=False,
                rtscts=False,
            )

            self.port = target_port

        except (serial.SerialException, OSError) as exc:
            print(f"[ESP32] Could not open {target_port}: {exc}")
            self.ser = None
            return False

        self._rx_buffer.clear()
        self._discarding_rx_line = False

        # Opening a USB serial port can reset many ESP32 boards.
        time.sleep(self.startup_delay)

        try:
            with self._io_lock:
                if self.ser is None or not self.ser.is_open:
                    return False

                # No command has been sent yet, so startup output
                # can be discarded before the handshake begins.
                self.ser.reset_input_buffer()

        except (serial.SerialException, OSError) as exc:
            print(f"[ESP32] Serial initialization failed: {exc}")
            self._close_port()
            return False

        for attempt in range(1, retries + 1):
            response = self.send_command("PING")

            if response == "PONG":
                self._connected = True
                self._start_heartbeat()

                version = self.get_version()
                status = self.get_status()

                if status == "STATUS:LED_ON":
                    self._set_led_cache(True)
                elif status == "STATUS:LED_OFF":
                    self._set_led_cache(False)
                else:
                    self._set_led_cache(None)

                print(f"[ESP32] Connected on {self.port}.")
                print(f"[ESP32] Firmware: {version or 'unknown'}")
                print(f"[ESP32] Initial LED status: {status or 'unknown'}")

                return True

            print(
                f"[ESP32] Handshake attempt "
                f"{attempt}/{retries} failed."
            )

            if attempt < retries:
                time.sleep(0.2)

        print("[ESP32] Handshake failed: no valid PONG received.")
        self._close_port()
        return False

    # ---------------------------------------------------------
    # High-level LED and information methods
    # ---------------------------------------------------------

    def set_led(self, turn_on: bool, force: bool = False) -> bool:
        """
        Set the LED state.

        The cache avoids duplicate commands in the CV loop.
        force=True sends the command even if the cache matches.
        """
        if not isinstance(turn_on, bool):
            raise TypeError("turn_on must be a bool")

        if not self.is_connected:
            print("[ESP32] Cannot control LED: not connected.")
            return False

        with self._state_lock:
            cached_state = self.led_is_on

        if not force and cached_state is turn_on:
            return True

        cmd = "LED_ON" if turn_on else "LED_OFF"
        expected = f"ACK:{cmd}"

        response = self.send_command(cmd)

        if response == expected:
            self._set_led_cache(turn_on)
            return True

        self._set_led_cache(None)
        print(
            f"[ESP32] {cmd} was not confirmed. "
            f"Response: {response!r}"
        )
        return False

    def turn_on(self) -> bool:
        return self.set_led(True)

    def turn_off(self) -> bool:
        return self.set_led(False)

    def get_status(self) -> Optional[str]:
        response = self.send_command("STATUS")

        if response == "STATUS:LED_ON":
            self._set_led_cache(True)
        elif response == "STATUS:LED_OFF":
            self._set_led_cache(False)

        return response

    def get_version(self) -> Optional[str]:
        return self.send_command("VERSION")

    # ---------------------------------------------------------
    # Heartbeat management
    # ---------------------------------------------------------

    def _start_heartbeat(self) -> None:
        if (
            self._heartbeat_thread is not None
            and self._heartbeat_thread.is_alive()
        ):
            return

        self._stop_event.clear()

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="ESP32-Heartbeat",
            daemon=True,
        )

        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        """
        Send periodic PING commands.

        The interval is scheduled against monotonic time. A delayed
        transaction will not cause an immediate burst of catch-up pings.
        """
        next_ping = time.monotonic() + self.heartbeat_interval

        while not self._stop_event.is_set():
            delay = max(0.0, next_ping - time.monotonic())

            if self._stop_event.wait(delay):
                break

            if not self.is_connected:
                break

            response = self.send_command("PING")

            if response == "PONG":
                if self._consecutive_heartbeat_failures:
                    print("[ESP32] Heartbeat recovered.")

                self._consecutive_heartbeat_failures = 0

            else:
                self._consecutive_heartbeat_failures += 1
                self._set_led_cache(None)

                if self._consecutive_heartbeat_failures == 1:
                    print(
                        "[ESP32] Warning: heartbeat response "
                        "was not received."
                    )

                elif self._consecutive_heartbeat_failures % 3 == 0:
                    print(
                        "[ESP32] Warning: repeated heartbeat "
                        "failures; check USB, port, and firmware."
                    )

            next_ping += self.heartbeat_interval

            # Avoid sending a burst if an operation took too long.
            now = time.monotonic()

            if next_ping <= now:
                next_ping = now + self.heartbeat_interval

    # ---------------------------------------------------------
    # Shutdown
    # ---------------------------------------------------------

    def _close_port(self) -> None:
        """Close the serial port safely."""
        with self._io_lock:
            try:
                if self.ser is not None and self.ser.is_open:
                    try:
                        self.ser.cancel_read()
                    except (AttributeError, NotImplementedError):
                        pass
                    self.ser.close()
            except (serial.SerialException, OSError) as exc:
                print(f"[ESP32] Error while closing serial port: {exc}")
            finally:
                self.ser = None
                self._connected = False
                self._set_led_cache(None)

    def disconnect(self) -> None:
        """
        Stop heartbeats, attempt LED_OFF, then close the port.

        If USB communication has failed, the LED_OFF command cannot
        be guaranteed. The ESP32 firmware failsafe is the fallback.
        """
        self._closing = True
        self._stop_event.set()

        thread = self._heartbeat_thread

        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=self.timeout + 1.0)

        if self.ser is not None and self.ser.is_open:
            # Bypass the cache: always attempt the OFF command.
            response = self.send_command("LED_OFF")

            if response != "ACK:LED_OFF":
                print(
                    "[ESP32] Could not confirm LED_OFF during "
                    "shutdown. Firmware failsafe may be needed."
                )

        self._close_port()
        self._heartbeat_thread = None

        print("[ESP32] Disconnected.")


# =============================================================
# Standalone connection and LED test
# =============================================================

def main():
    # Use port=None for auto-discovery.
    # For a specific board, use port="COM3" or the actual device path.
    esp = ESP32Controller(
        port=None,
        baudrate=115200,
        timeout=0.5,
        heartbeat_interval=1.5,
        startup_delay=1.5,
        failsafe_timeout=5.0,
    )

    try:
        if not esp.connect():
            print("[TEST] Connection failed.")
            return

        print("[TEST] Turning LED ON.")

        if not esp.turn_on():
            print("[TEST] LED_ON was not confirmed.")
            return

        print(
            "[TEST] Waiting 6 seconds with heartbeat active. "
            "The LED should remain on."
        )

        time.sleep(6)

        print("[TEST] Status:", esp.get_status())

        print("[TEST] Turning LED OFF.")

        if esp.turn_off():
            print("[TEST] LED_OFF confirmed.")
        else:
            print("[TEST] LED_OFF was not confirmed.")

    except KeyboardInterrupt:
        print("\n[TEST] Interrupted by user.")

    finally:
        esp.disconnect()


if __name__ == "__main__":
    main()
    