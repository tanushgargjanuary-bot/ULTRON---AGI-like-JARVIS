"""scripts/make_banner.py — draw the animated picture at the top of the readme.

    python scripts/make_banner.py

Two honest rules for this file:

1. **It is an illustration, not a screenshot.** It is drawn from the same palette
   the HUD uses, and the readme says so in the caption. A picture that pretends to
   be a recording of a window that was never photographed is exactly the kind of
   claim this project keeps removing.
2. **It is generated, so it can be changed.** A hand-made GIF in a repository is a
   file nobody can edit. This one is a script, forty frames, and the readme links
   here.

Output: docs/img/hud-states.gif — three states, one breath each.
"""

from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "hud-states.gif"

WIDTH, HEIGHT = 560, 210
FRAMES = 40
FRAME_MS = 90

BACKGROUND = (4, 8, 12)
TEAL = (0, 214, 200)
TEAL_DIM = (10, 92, 96)
VIOLET = (150, 120, 255)
GREEN = (90, 230, 150)
TEXT = (198, 226, 230)

STATES = (
    ("LISTENING", GREEN, "hears you"),
    ("THINKING", VIOLET, "works out the answer"),
    ("SPEAKING", TEAL, "answers out loud"),
)


def _arc(draw, cx, cy, radius, start, span, colour, width=2):
    box = [cx - radius, cy - radius, cx + radius, cy + radius]
    draw.arc(box, start=start, end=start + span, fill=colour, width=width)


def frame(index: int):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    phase = index / FRAMES
    step = int(phase * len(STATES)) % len(STATES)
    name, accent, caption = STATES[step]
    local = (phase * len(STATES)) % 1.0            # progress inside one state

    cx, cy = 120, HEIGHT / 2
    breath = 0.5 + 0.5 * math.sin(local * math.tau)   # 0..1, one breath a state

    # the outer rings, drifting at three speeds
    for radius, speed, colour, width in ((86, 1.2, TEAL_DIM, 2),
                                         (70, -1.8, accent, 2),
                                         (54, 2.6, TEAL_DIM, 1)):
        for k in range(3):
            start = (local * 360 * speed + k * 120) % 360
            _arc(draw, cx, cy, radius, start, 70, colour, width)

    # the core: a soft dot that breathes with the state
    core = 10 + 6 * breath
    for i in range(6, 0, -1):
        shade = tuple(int(c * (i / 12 + 0.25 * breath)) for c in accent)
        draw.ellipse([cx - core * i / 3, cy - core * i / 3,
                      cx + core * i / 3, cy + core * i / 3], outline=shade)
    draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=accent)

    # the three labels sit in a column, the active one lit
    top = 34
    for row, (title, colour, _text) in enumerate(STATES):
        y = top + row * 44
        active = row == step
        pill = accent if active else (28, 40, 44)
        draw.rounded_rectangle([210, y, 210 + (150 if active else 132), y + 26],
                               radius=13, fill=pill)
        draw.text((224, y + 7), title, fill=BACKGROUND if active else (120, 150, 154))

    draw.text((210, top + 3 * 44 + 14), f"Ultron {caption}", fill=TEXT)
    return image


def main() -> int:
    try:
        from PIL import Image           # noqa: F401
    except ImportError:
        print("Pillow is not installed. Run: pip install pillow")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    images = [frame(i) for i in range(FRAMES)]
    images[0].save(OUT, save_all=True, append_images=images[1:], duration=FRAME_MS,
                   loop=0, optimize=True)
    size = OUT.stat().st_size
    print(f"wrote {OUT.relative_to(ROOT)} — {FRAMES} frames, {size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
