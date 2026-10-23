from backend.gestures import DebounceResult, Gesture
from backend.interface import InterfaceModel, Notice, SetLed


def res(active, progress=1.0, fired=None):
    return DebounceResult(active, progress, fired)


def test_thumbs_up_requires_focus():
    m = InterfaceModel(focus_timeout_s=5)
    fx = m.update(res(Gesture.THUMBS_UP, fired=Gesture.THUMBS_UP), now=0)
    assert not any(isinstance(e, SetLed) for e in fx)
    assert any(isinstance(e, Notice) for e in fx)


def test_point_then_thumbs_up_turns_on():
    m = InterfaceModel(focus_timeout_s=5)
    m.update(res(Gesture.POINT), now=0)
    assert m.focus == "LIGHT"
    fx = m.update(res(Gesture.THUMBS_UP, fired=Gesture.THUMBS_UP), now=1)
    assert SetLed(True) in fx


def test_focus_expires():
    m = InterfaceModel(focus_timeout_s=5)
    m.update(res(Gesture.POINT), now=0)
    m.update(res(Gesture.NONE, 0.0), now=6)
    assert m.focus is None
    fx = m.update(res(Gesture.THUMBS_UP, fired=Gesture.THUMBS_UP), now=6.1)
    assert SetLed(True) not in fx


def test_open_palm_always_turns_off():
    m = InterfaceModel()
    fx = m.update(res(Gesture.OPEN_PALM, fired=Gesture.OPEN_PALM), now=0)
    assert SetLed(False) in fx


def test_fan_and_temp_are_disabled():
    snap = InterfaceModel().snapshot()
    enabled = {i["id"]: i["enabled"] for i in snap["items"]}
    assert enabled == {"LIGHT": True, "FAN": False, "TEMP": False}
