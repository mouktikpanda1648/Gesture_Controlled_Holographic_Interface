"""Hand-gesture classification from MediaPipe's 21 hand landmarks.

The classifier is a pure function of the landmark geometry so it can be unit
tested without a camera.  Finger state is decided from distances to the wrist
(rotation-invariant); only THUMBS_UP additionally requires the thumb to point
upward on screen.

Landmark indices follow the MediaPipe Hand Landmarker topology.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, Sequence

Point = Sequence[float]  # (x, y[, z]) in normalised image coordinates

WRIST = 0
THUMB_MCP, THUMB_IP, THUMB_TIP = 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_MCP, RING_PIP, RING_TIP = 13, 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20

HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)


class Gesture(str, Enum):
    NONE = "NONE"            # no hand in view
    UNKNOWN = "UNKNOWN"      # hand present, no recognised pose
    FIST = "FIST"            # recognised but intentionally unmapped (safe "rest" pose)
    POINT = "POINT"          # index finger only  -> highlight LIGHT
    THUMBS_UP = "THUMBS_UP"  # confirmation       -> LED_ON
    OPEN_PALM = "OPEN_PALM"  # all fingers out    -> LED_OFF


# Tunable thresholds -------------------------------------------------------
FINGER_EXTEND_RATIO = 1.08   # tip must be this much farther from wrist than PIP
THUMB_EXTEND_RATIO = 0.50    # thumb tip <-> index MCP distance, in hand sizes
THUMB_UP_MIN_RISE = 0.55     # thumb tip must be this many hand sizes above its MCP


def _dist(a: Point, b: Point, aspect: float) -> float:
    return math.hypot((a[0] - b[0]) * aspect, a[1] - b[1])


def _finger_extended(lm: Sequence[Point], pip: int, tip: int, aspect: float) -> bool:
    return _dist(lm[tip], lm[WRIST], aspect) > _dist(lm[pip], lm[WRIST], aspect) * FINGER_EXTEND_RATIO


def _thumb_extended(lm: Sequence[Point], hand_size: float, aspect: float) -> bool:
    tip_far = _dist(lm[THUMB_TIP], lm[INDEX_MCP], aspect)
    ip_far = _dist(lm[THUMB_IP], lm[INDEX_MCP], aspect)
    return tip_far > THUMB_EXTEND_RATIO * hand_size and tip_far > ip_far


def classify(landmarks: Sequence[Point] | None, aspect: float = 1.0) -> Gesture:
    """Classify one hand.

    ``aspect`` is frame width / height; it corrects the anisotropy of
    normalised coordinates so distances are comparable in x and y.
    """
    if not landmarks or len(landmarks) < 21:
        return Gesture.NONE

    lm = landmarks
    hand_size = _dist(lm[WRIST], lm[MIDDLE_MCP], aspect)
    if hand_size < 1e-4:
        return Gesture.UNKNOWN

    index = _finger_extended(lm, INDEX_PIP, INDEX_TIP, aspect)
    middle = _finger_extended(lm, MIDDLE_PIP, MIDDLE_TIP, aspect)
    ring = _finger_extended(lm, RING_PIP, RING_TIP, aspect)
    pinky = _finger_extended(lm, PINKY_PIP, PINKY_TIP, aspect)
    thumb = _thumb_extended(lm, hand_size, aspect)
    fingers = (index, middle, ring, pinky)

    if all(fingers):
        return Gesture.OPEN_PALM

    if index and not (middle or ring or pinky):
        return Gesture.POINT

    if not any(fingers):
        if thumb:
            rise = lm[THUMB_MCP][1] - lm[THUMB_TIP][1]          # +ve = tip above MCP
            sideways = abs(lm[THUMB_TIP][0] - lm[THUMB_MCP][0]) * aspect
            if rise > THUMB_UP_MIN_RISE * hand_size and rise > sideways:
                return Gesture.THUMBS_UP
            return Gesture.UNKNOWN
        return Gesture.FIST

    return Gesture.UNKNOWN


# --------------------------------------------------------------------------
# Temporal filtering
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DebounceResult:
    active: Gesture          # gesture currently considered held
    progress: float          # 0..1 hold progress towards activation
    fired: Gesture | None    # set for exactly one update when a hold completes


class GestureDebouncer:
    """Turns noisy per-frame classifications into deliberate, edge-triggered actions.

    * A new gesture must persist for ``switch_s`` (neutral/lost: ``lost_grace_s``)
      before it replaces the current one, which suppresses single-frame flicker.
    * A gesture with a configured hold time *fires once* when held long enough;
      it must change before it can fire again (no repeat triggers).
    """

    NEUTRAL = frozenset({Gesture.NONE, Gesture.UNKNOWN, Gesture.FIST})

    def __init__(
        self,
        hold_times: Mapping[str, float],
        switch_s: float = 0.08,
        lost_grace_s: float = 0.35,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._hold = {Gesture(k): float(v) for k, v in hold_times.items()}
        self._switch_s = switch_s
        self._lost_grace_s = lost_grace_s
        self._clock = clock
        self.reset()

    def reset(self) -> None:
        self._active = Gesture.NONE
        self._active_since = self._clock()
        self._fired = False
        self._pending: Gesture | None = None
        self._pending_since = 0.0

    def update(self, gesture: Gesture, now: float | None = None) -> DebounceResult:
        now = self._clock() if now is None else now

        if gesture == self._active:
            self._pending = None
        else:
            if self._pending != gesture:
                self._pending, self._pending_since = gesture, now
            delay = self._lost_grace_s if gesture in self.NEUTRAL else self._switch_s
            if now - self._pending_since >= delay:
                self._active = gesture
                self._active_since = self._pending_since
                self._fired = False
                self._pending = None

        hold = self._hold.get(self._active)
        progress = 0.0
        fired: Gesture | None = None
        if hold is not None:
            progress = 1.0 if hold <= 0 else min(1.0, (now - self._active_since) / hold)
            if progress >= 1.0 and not self._fired:
                self._fired = True
                fired = self._active
        return DebounceResult(self._active, progress, fired)
