"""Task 4 helper: webcam window with hand landmarks and the live gesture label.

    python -m backend.preview            # q or Esc to quit

Use it to check detection in your exhibition lighting.  If a gesture is
misread, adjust the thresholds at the top of backend/gestures.py.
"""

from __future__ import annotations

import argparse
import time

import cv2

from .config import Settings
from .gestures import HAND_CONNECTIONS, classify
from .tracker import HandDetector, open_camera


def main() -> None:
    p = argparse.ArgumentParser(description="Hand landmark / gesture preview")
    p.add_argument("--camera", type=int, default=0)
    a = p.parse_args()

    settings = Settings(camera_index=a.camera, mirror=True)
    cap = open_camera(settings)
    if cap is None:
        raise SystemExit(f"Cannot open camera {a.camera}")
    detector = HandDetector(settings)
    last, fps = time.monotonic(), 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            frame = cv2.flip(frame, 1)  # detector already mirrors x, so mirror the picture too
            h, w = frame.shape[:2]
            lms = detector.detect(cv2.flip(frame, 1))  # feed the un-mirrored frame
            gesture = classify(lms, w / h)
            if lms:
                pts = [(int(x * w), int(y * h)) for x, y, _ in lms]
                for i, j in HAND_CONNECTIONS:
                    cv2.line(frame, pts[i], pts[j], (255, 232, 77), 2, cv2.LINE_AA)
                for pt in pts:
                    cv2.circle(frame, pt, 4, (255, 255, 255), -1, cv2.LINE_AA)
            now = time.monotonic()
            fps = 0.9 * fps + 0.1 / max(now - last, 1e-6) if fps else 1.0
            last = now
            cv2.putText(frame, f"{gesture.value}   {fps:4.1f} fps", (12, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow("Hand preview (q to quit)", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        detector.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
