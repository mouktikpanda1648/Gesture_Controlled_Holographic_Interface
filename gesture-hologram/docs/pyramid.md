# Pyramid & display setup (Tasks 1 and 5)

This is a **Pepper's-ghost** effect, not a true 3-D hologram: a transparent pyramid reflects four
copies of the interface so a floating image appears inside it. It works best in a dim room with the
screen at full brightness.

## Build the pyramid

```bash
python scripts/pyramid_template.py --base 10 --top 70      # → docs/pyramid_template.svg
```

* Four identical isosceles trapezoids, small end down, faces at **45°** (height = (top − base) / 2).
* Print the SVG at **100 %** and check the 50 mm scale bar. Trace onto clear PET/acrylic with a fine
  marker, cut with a sharp blade against a straightedge, then join the edges with clear tape.
* The default (10 mm / 70 mm) suits a laptop; scale both numbers up for a larger monitor.
* Put the pyramid on a black base so only the reflections are visible.

## Show the interface

1. Run the app, open the page full-screen on the laptop/monitor, press **H** (hologram view).
2. Press **G** to show the alignment guide: the small square marks the pyramid footprint.
   Centre the pyramid's small base on it.
3. Tune with **+ / −** (image size) and **[ / ]** (distance from centre) until the reflections line up
   with the faces. A good start is an image cell about as wide as the pyramid's top edge.
4. Turn the guide off (**G**). Switch back to the operator view with **H** — the sliders persist.

The bottom copy is mirrored vertically and the other three are rotations of it, which is the
orientation for a pyramid standing small-end-down. If the floating image looks upside-down or
back-to-front on your build, adjust the transform in `frontend/js/hologram.js`.
