"""Pre-download the MediaPipe hand model so the first run works offline.

    python scripts/download_model.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import DEFAULT_MODEL  # noqa: E402
from backend.tracker import ensure_model  # noqa: E402

if __name__ == "__main__":
    path = ensure_model(DEFAULT_MODEL)
    print(f"Model ready: {path} ({path.stat().st_size / 1e6:.1f} MB)")
