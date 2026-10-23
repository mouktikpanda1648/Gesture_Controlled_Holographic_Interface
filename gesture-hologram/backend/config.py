"""Runtime configuration for the gesture-hologram backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
DEFAULT_MODEL = Path(__file__).resolve().parent / "models" / "hand_landmarker.task"

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)


@dataclass(slots=True)
class Settings:
    # --- web server -------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = False

    # --- camera / vision --------------------------------------------------
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    mirror: bool = True  # selfie view: moving the hand right moves it right on screen
    model_path: Path = DEFAULT_MODEL
    min_detection_confidence: float = 0.6
    min_tracking_confidence: float = 0.5

    # --- ESP32 ------------------------------------------------------------
    serial_port: str | None = None  # None = auto-detect
    baudrate: int = 115200

    # --- gesture timing (seconds a gesture must be held to trigger) --------
    hold_point_s: float = 0.15
    hold_confirm_s: float = 0.60
    hold_off_s: float = 0.50
    focus_timeout_s: float = 5.0  # how long LIGHT stays highlighted after pointing

    # --- development ------------------------------------------------------
    simulate_camera: bool = False
    simulate_esp32: bool = False
    allow_inject: bool = False  # accept keyboard-injected gestures from the UI

    hold_times: dict[str, float] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.hold_times = {
            "POINT": self.hold_point_s,
            "THUMBS_UP": self.hold_confirm_s,
            "OPEN_PALM": self.hold_off_s,
        }
        if self.simulate_camera:
            self.allow_inject = True
