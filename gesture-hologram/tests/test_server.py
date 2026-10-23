"""End-to-end server test in simulation mode (no camera, no ESP32)."""
import asyncio
import json

import pytest
from aiohttp import ClientSession, WSMsgType
from aiohttp.test_utils import TestClient, TestServer

from backend.config import Settings
from backend.server import create_app


async def next_state(ws, predicate, timeout=5.0):
    async def _wait():
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("type") == "state" and predicate(data):
                    return data
    return await asyncio.wait_for(_wait(), timeout)


@pytest.fixture
async def client():
    app = create_app(Settings(simulate_camera=True, simulate_esp32=True))
    async with TestClient(TestServer(app)) as c:
        yield c


async def test_index_and_health(client):
    r = await client.get("/")
    assert r.status == 200 and "Holo-Link" in await r.text()
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    r = await client.get("/api/health")
    assert (await r.json())["ok"] is True
    assert (await client.get("/js/main.js")).status == 200


async def test_point_then_thumbs_up_then_palm(client):
    async with client.ws_connect("/ws") as ws:
        hello = json.loads((await ws.receive()).data)
        assert hello["type"] == "hello" and hello["inject"] is True

        await ws.send_json({"type": "inject", "gesture": "POINT"})
        s = await next_state(ws, lambda d: d["ui"]["focus"] == "LIGHT")
        assert s["link"]["led"] == "off"

        await ws.send_json({"type": "inject", "gesture": "THUMBS_UP"})
        s = await next_state(ws, lambda d: d["link"]["led"] == "on")

        await ws.send_json({"type": "inject", "gesture": "OPEN_PALM"})
        await next_state(ws, lambda d: d["link"]["led"] == "off")


async def test_thumbs_up_without_focus_does_nothing(client):
    async with client.ws_connect("/ws") as ws:
        await ws.send_json({"type": "inject", "gesture": "THUMBS_UP"})
        with pytest.raises(asyncio.TimeoutError):
            await next_state(ws, lambda d: d["link"]["led"] == "on", timeout=1.5)


async def test_manual_command_and_bad_input(client):
    async with client.ws_connect("/ws") as ws:
        await ws.send_str("not json")
        await ws.send_json({"type": "command", "cmd": "REBOOT"})       # not whitelisted
        await ws.send_json({"type": "command", "cmd": "LED_ON"})
        await next_state(ws, lambda d: d["link"]["led"] == "on")


async def test_cross_origin_websocket_rejected(client):
    async with ClientSession() as s:
        url = str(client.make_url("/ws"))
        with pytest.raises(Exception):
            await s.ws_connect(url, headers={"Origin": "https://evil.example"})
