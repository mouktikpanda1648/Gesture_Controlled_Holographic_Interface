"""SerialLedBridge + the project's ESP32Controller against a firmware model on a pty."""
import asyncio
import sys

import pytest

from backend.config import Settings
from backend.hardware import SerialLedBridge
from fake_esp32 import FakeESP32

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="needs POSIX pty")


async def wait_for(pred, timeout=8.0):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if pred():
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.fixture
async def rig():
    fake = FakeESP32().start()
    msgs = []
    bridge = SerialLedBridge(Settings(serial_port=fake.path), lambda lvl, m: msgs.append((lvl, m)))
    await bridge.start()
    assert await wait_for(lambda: bridge.snapshot()["status"] == "connected")
    yield fake, bridge, msgs
    await bridge.stop()
    fake.stop()


async def test_connects_and_reports_firmware(rig):
    fake, bridge, _ = rig
    snap = bridge.snapshot()
    assert snap["firmware"] == "1.0" and snap["led"] == "off"
    assert "PING" in fake.log and "VERSION" in fake.log


async def test_led_on_off_round_trip(rig):
    fake, bridge, _ = rig
    assert await bridge.set_led(True)
    assert fake.led is True and bridge.snapshot()["led"] == "on"
    assert await bridge.set_led(False)
    assert fake.led is False and bridge.snapshot()["led"] == "off"


async def test_heartbeat_keeps_led_on_past_failsafe(rig):
    fake, bridge, _ = rig
    fake.failsafe_s = 2.5                    # shorten the wait; heartbeat is every 1.5 s
    assert await bridge.set_led(True)
    await asyncio.sleep(4.0)
    assert fake.led is True, "heartbeat should have prevented the firmware failsafe"


async def test_shutdown_turns_led_off():
    fake = FakeESP32().start()
    bridge = SerialLedBridge(Settings(serial_port=fake.path), lambda *_: None)
    await bridge.start()
    assert await wait_for(lambda: bridge.snapshot()["status"] == "connected")
    await bridge.set_led(True)
    await bridge.stop()
    assert fake.led is False
    fake.stop()
