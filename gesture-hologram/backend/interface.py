"""Interface state machine: maps debounced gestures to menu focus and LED actions.

Basic build (per the project guide):
    point      -> highlight LIGHT
    thumbs up  -> LED_ON   (only while LIGHT is highlighted)
    open palm  -> LED_OFF  (always honoured — turning things off must never be blocked)

FAN and TEMP are listed in the menu but disabled until the hardware exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gestures import DebounceResult, Gesture


@dataclass(frozen=True, slots=True)
class MenuItem:
    id: str
    label: str
    enabled: bool
    note: str = ""


@dataclass(frozen=True, slots=True)
class SetLed:
    on: bool
    source: str = "gesture"


@dataclass(frozen=True, slots=True)
class Notice:
    message: str


Effect = SetLed | Notice

DEFAULT_ITEMS: tuple[MenuItem, ...] = (
    MenuItem("LIGHT", "LIGHT", True),
    MenuItem("FAN", "FAN", False, "Not installed"),
    MenuItem("TEMP", "TEMP", False, "Not installed"),
)


class InterfaceModel:
    def __init__(self, focus_timeout_s: float = 5.0, items: tuple[MenuItem, ...] = DEFAULT_ITEMS) -> None:
        self.items = items
        self.focus_timeout_s = focus_timeout_s
        self.focus: str | None = None
        self._focus_until = 0.0

    def update(self, result: DebounceResult, now: float) -> list[Effect]:
        effects: list[Effect] = []

        if self.focus and now >= self._focus_until:
            self.focus = None

        if result.active == Gesture.POINT and result.progress >= 1.0:
            if self.focus != "LIGHT":
                effects.append(Notice("LIGHT selected"))
            self.focus = "LIGHT"
            self._focus_until = now + self.focus_timeout_s

        if result.fired == Gesture.THUMBS_UP:
            if self.focus == "LIGHT":
                effects.append(SetLed(True))
                self._focus_until = now + self.focus_timeout_s
            else:
                effects.append(Notice("Point at LIGHT first, then give a thumbs up"))
        elif result.fired == Gesture.OPEN_PALM:
            effects.append(SetLed(False))

        return effects

    def snapshot(self) -> dict:
        return {
            "focus": self.focus,
            "items": [
                {"id": i.id, "label": i.label, "enabled": i.enabled, "note": i.note}
                for i in self.items
            ],
        }
