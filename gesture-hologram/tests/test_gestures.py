import pytest

from backend.gestures import Gesture, GestureDebouncer, classify
from hand_fixtures import make_hand


def test_no_hand():
    assert classify(None) is Gesture.NONE
    assert classify([]) is Gesture.NONE


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        (dict(index=True), Gesture.POINT),
        (dict(index=True, thumb="side"), Gesture.POINT),
        (dict(index=True, middle=True, ring=True, pinky=True, thumb="side"), Gesture.OPEN_PALM),
        (dict(index=True, middle=True, ring=True, pinky=True), Gesture.OPEN_PALM),
        (dict(thumb="up"), Gesture.THUMBS_UP),
        (dict(), Gesture.FIST),
        (dict(index=True, middle=True), Gesture.UNKNOWN),   # peace sign is not mapped
        (dict(thumb="side"), Gesture.UNKNOWN),               # thumb out sideways, not up
    ],
)
def test_classify(kwargs, expected):
    assert classify(make_hand(**kwargs)) is expected


def test_aspect_ratio_does_not_break_pointing():
    assert classify(make_hand(index=True), aspect=16 / 9) is Gesture.POINT


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def run(deb, clock, gesture, seconds, step=0.02):
    fired = []
    end = clock.t + seconds
    last = None
    while clock.t < end:
        clock.t += step
        last = deb.update(gesture, clock.t)
        if last.fired:
            fired.append(last.fired)
    return last, fired


def test_hold_fires_exactly_once():
    c = Clock()
    deb = GestureDebouncer({"THUMBS_UP": 0.6}, clock=c)
    res, fired = run(deb, c, Gesture.THUMBS_UP, 2.0)
    assert fired == [Gesture.THUMBS_UP]
    assert res.progress == 1.0


def test_short_hold_does_not_fire():
    c = Clock()
    deb = GestureDebouncer({"THUMBS_UP": 0.6}, clock=c)
    _, fired = run(deb, c, Gesture.THUMBS_UP, 0.4)
    assert fired == []


def test_single_frame_flicker_is_ignored():
    c = Clock()
    deb = GestureDebouncer({"OPEN_PALM": 0.5}, clock=c)
    run(deb, c, Gesture.OPEN_PALM, 0.3)
    run(deb, c, Gesture.UNKNOWN, 0.04)       # one-or-two bad frames
    _, fired = run(deb, c, Gesture.OPEN_PALM, 0.4)
    assert fired == [Gesture.OPEN_PALM]


def test_refires_only_after_release():
    c = Clock()
    deb = GestureDebouncer({"OPEN_PALM": 0.3}, clock=c)
    _, f1 = run(deb, c, Gesture.OPEN_PALM, 1.0)
    run(deb, c, Gesture.NONE, 1.0)
    _, f2 = run(deb, c, Gesture.OPEN_PALM, 1.0)
    assert f1 == f2 == [Gesture.OPEN_PALM]
