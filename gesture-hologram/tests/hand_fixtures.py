"""Synthetic 21-point hands (normalised coords, y grows downward) for classifier tests."""

WRIST = (0.50, 0.90)
MCP = {"index": (0.44, 0.62), "middle": (0.50, 0.60), "ring": (0.56, 0.62), "pinky": (0.62, 0.66)}
BASE = {"index": 5, "middle": 9, "ring": 13, "pinky": 17}


def make_hand(index=False, middle=False, ring=False, pinky=False, thumb="folded"):
    lm = [WRIST] * 21
    lm = list(lm)
    flags = {"index": index, "middle": middle, "ring": ring, "pinky": pinky}
    for name, extended in flags.items():
        mx, my = MCP[name]
        i = BASE[name]
        lm[i] = (mx, my)
        if extended:
            lm[i + 1], lm[i + 2], lm[i + 3] = (mx, my - 0.08), (mx, my - 0.14), (mx, my - 0.19)
        else:  # curled into the palm
            lm[i + 1], lm[i + 2], lm[i + 3] = (mx, my - 0.07), (mx, my - 0.02), (mx, my + 0.02)
    lm[1] = (0.42, 0.84)
    lm[2] = (0.38, 0.76)
    if thumb == "up":
        lm[3], lm[4] = (0.35, 0.60), (0.33, 0.45)
    elif thumb == "side":
        lm[3], lm[4] = (0.30, 0.74), (0.20, 0.72)
    else:  # folded across the palm
        lm[3], lm[4] = (0.44, 0.70), (0.47, 0.66)
    return lm
