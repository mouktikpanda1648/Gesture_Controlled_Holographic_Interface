"""Webcam capture + MediaPipe Hand Landmarker (Tasks API) on a worker thread."""

from __future__ import annotations

import logging
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import MODEL_URL, Settings
from .gestures import Gesture, classify

log = logging.getLogger("hologram.tracker")

Landmarks = list[tuple[float, float, float]]


@dataclass(frozen=True, slots=True)
class Observation:
    t: float
    gesture: Gesture
    landmarks: Landmarks | None
    fps: float


StatusCallback = Callable[[str, str], None]        # (status, detail)
ObservationCallback = Callable[[Observation], None]


def ensure_model(path: Path, url: str = MODEL_URL) -> Path:
    """Return the model path, downloading it on first use."""
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading hand landmarker model (~7 MB) to %s", path)
    tmp = path.with_suffix(".part")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp, open(tmp, "wb") as fh:  # noqa: S310
            while chunk := resp.read(1 << 16):
                fh.write(chunk)
        tmp.replace(path)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"could not download the hand model ({exc}). Download it manually from\n  {url}\n"
            f"and save it as {path}"
        ) from exc
    return path


class HandDetector:
    """Thin wrapper around MediaPipe's HandLandmarker in VIDEO mode."""

    def __init__(self, settings: Settings) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        self._mirror = settings.mirror
        self._last_ts = 0
        model = ensure_model(Path(settings.model_path))
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=settings.min_detection_confidence,
            min_hand_presence_confidence=settings.min_detection_confidence,
            min_tracking_confidence=settings.min_tracking_confidence,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

    def detect(self, frame_bgr) -> Landmarks | None:
        import cv2

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        ts = max(int(time.monotonic() * 1000), self._last_ts + 1)  # must strictly increase
        self._last_ts = ts
        result = self._landmarker.detect_for_video(image, ts)
        if not result.hand_landmarks:
            return None
        hand = result.hand_landmarks[0]
        if self._mirror:
            return [(1.0 - p.x, p.y, p.z) for p in hand]
        return [(p.x, p.y, p.z) for p in hand]

    def close(self) -> None:
        self._landmarker.close()


def open_camera(settings: Settings):
    import cv2

    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
    cap = cv2.VideoCapture(settings.camera_index, backend)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.frame_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.frame_height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


class CameraTracker:
    """Runs capture + detection on a daemon thread and reports observations."""

    RETRY_DELAY_S = 3.0

    def __init__(self, settings: Settings, on_observation: ObservationCallback, on_status: StatusCallback) -> None:
        self._s = settings
        self._on_obs = on_observation
        self._on_status = on_status
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="camera-tracker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def _run(self) -> None:
        detector: HandDetector | None = None
        try:
            self._on_status("starting", "Loading hand model")
            detector = HandDetector(self._s)
        except Exception as exc:  # model download / import problems
            log.exception("Could not start hand detector")
            self._on_status("error", f"Hand model unavailable: {exc}")
            return

        try:
            while not self._stop.is_set():
                cap = open_camera(self._s)
                if cap is None:
                    self._on_status("error", f"Cannot open camera {self._s.camera_index}")
                    self._stop.wait(self.RETRY_DELAY_S)
                    continue
                self._on_status("ok", f"Camera {self._s.camera_index}")
                self._capture_loop(cap, detector)
                cap.release()
        finally:
            detector.close()

    def _capture_loop(self, cap, detector: HandDetector) -> None:
        fps, last = 0.0, time.monotonic()
        failures = 0
        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                failures += 1
                if failures > 30:
                    self._on_status("error", "Camera stopped delivering frames")
                    return
                time.sleep(0.02)
                continue
            failures = 0

            h, w = frame.shape[:2]
            landmarks = detector.detect(frame)
            gesture = classify(landmarks, aspect=w / h)

            now = time.monotonic()
            dt = now - last
            last = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt
            self._on_obs(Observation(now, gesture, landmarks, fps))
