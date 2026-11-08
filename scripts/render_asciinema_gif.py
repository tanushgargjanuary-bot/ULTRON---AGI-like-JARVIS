"""Render an asciinema v2 cast to a small terminal-window GIF.

Demo-only dependencies: ``pip install -r requirements-demo.txt``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pyte
from PIL import Image, ImageDraw, ImageFont


BASE = {
    "black": "#000000", "red": "#cd3131", "green": "#0dbc79", "yellow": "#e5e510",
    "blue": "#2472c8", "magenta": "#bc3fbc", "cyan": "#11a8cd", "white": "#e5e5e5",
    "brightblack": "#666666", "brightred": "#f14c4c", "brightgreen": "#23d18b",
    "brightyellow": "#f5f543", "brightblue": "#3b8eea", "brightmagenta": "#d670d6",
    "brightcyan": "#29b8db", "brightwhite": "#ffffff",
}


def _colour(value, foreground=True):
    if value in (None, "default"):
        return "#d8f8ff" if foreground else "#070b14"
    if value in BASE:
        return BASE[value]
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "#d8f8ff" if foreground else "#070b14"
    if number < 16:
        return list(BASE.values())[number]
    if number < 232:
        number -= 16
        levels = (0, 95, 135, 175, 215, 255)
        r, rem = divmod(number, 36)
        g, b = divmod(rem, 6)
        return "#{:02x}{:02x}{:02x}".format(levels[r], levels[g], levels[b])
    gray = 8 + (number - 232) * 10
    return "#{0:02x}{0:02x}{0:02x}".format(max(0, min(255, gray)))


def _font(size):
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
        "C:/Windows/Fonts/consola.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _render(screen, cols, rows, font, cell_w, cell_h):
    margin_x, top, bottom = 24, 58, 22
    width = margin_x * 2 + cols * cell_w
    height = top + rows * cell_h + bottom
    image = Image.new("RGB", (width, height), "#070b14")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((7, 7, width - 8, height - 8), radius=12,
                           fill="#080d17", outline="#167c98", width=2)
    draw.ellipse((22, 24, 33, 35), fill="#ff5f57")
    draw.ellipse((42, 24, 53, 35), fill="#febc2e")
    draw.ellipse((62, 24, 73, 35), fill="#28c840")
    draw.text((92, 21), "ULTRON  /  SCRIPTED TERMINAL PREVIEW", font=font, fill="#67eaff")

    for y in range(rows):
        line = screen.buffer[y]
        for x in range(cols):
            cell = line[x]
            px = margin_x + x * cell_w
            py = top + y * cell_h
            bg = _colour(cell.bg, foreground=False)
            if bg != "#070b14":
                draw.rectangle((px, py, px + cell_w, py + cell_h), fill=bg)
            value = cell.data or " "
            fg = _colour(cell.fg)
            if getattr(cell, "bold", False):
                fg = "#ffffff" if fg == "#d8f8ff" else fg
            draw.text((px, py - 1), value, font=font, fill=fg)
    draw.text((margin_x, height - 22), "OFFLINE DEMO · NO COMPUTER OR WEB ACTIONS", font=font,
              fill="#6b8794")
    return image


def render(cast_path: Path, gif_path: Path):
    lines = cast_path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    cols, rows = int(header["width"]), int(header["height"])
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    font_size = max(12, min(17, 820 // max(cols, 1)))
    font = _font(font_size)
    cell_w = max(8, round(font_size * 0.62))
    cell_h = round(font_size * 1.5)
    frames, durations, previous = [], [], 0.0
    events = [json.loads(line) for line in lines[1:] if line.strip()]
    for index, event in enumerate(events):
        at, kind, payload = event[:3]
        if kind != "o":
            continue
        stream.feed(payload)
        frames.append(_render(screen, cols, rows, font, cell_w, cell_h))
        next_at = events[index + 1][0] if index + 1 < len(events) else at + 1.5
        duration = max(120, min(1800, round((next_at - at) * 1000)))
        durations.append(duration)
        previous = at
    if not frames:
        raise ValueError("The asciinema recording contains no terminal output.")
    gif_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True, disposal=2)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python scripts/render_asciinema_gif.py input.cast output.gif")
    render(Path(sys.argv[1]), Path(sys.argv[2]))
