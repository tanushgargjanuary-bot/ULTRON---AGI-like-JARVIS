"""Deterministic, offline README tour recorded with asciinema.

The health issue is deliberately synthetic. This script does not open the HUD,
control the desktop, access user data, or contact the network.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from core.themes import THEMES
from custom_jarvis.health_center import HealthCenter


CYAN = "\033[38;5;51m"
BLUE = "\033[38;5;39m"
DIM = "\033[38;5;245m"
GREEN = "\033[38;5;48m"
AMBER = "\033[38;5;221m"
RESET = "\033[0m"


def pause(seconds=0.5):
    time.sleep(seconds)


def main():
    print("\033[2J\033[H", end="")
    print(f"{CYAN}╔══════════════════════════════════════════════════════════════════════╗")
    print("║  ULTRON  /  PERSONAL OPERATING LAYER                                 ║")
    print(f"╚══════════════════════════════════════════════════════════════════════╝{RESET}")
    print(f"{DIM}A native-OS assistant shell. The underlying OS stays in control.{RESET}\n")
    pause(0.7)

    print(f"{BLUE}CAPABILITIES{RESET}")
    print(f"  {GREEN}▸{RESET} Computer use     Window, keyboard and screen actions behind consent gates")
    print(f"  {GREEN}▸{RESET} Web search       Search current sources; return citations and snippets")
    print(f"  {GREEN}▸{RESET} Web reading      Public pages only; robots.txt checked; no block bypass")
    print(f"  {GREEN}▸{RESET} Health center    Persistent notices, ignore/dismiss, tested repair proposals")
    print(f"  {GREEN}▸{RESET} Visual themes    {', '.join(theme['label'] for theme in THEMES.values())}\n")
    pause(1.0)

    print(f"{BLUE}HEALTH CENTER  {DIM}— synthetic offline fixture{RESET}")
    with tempfile.TemporaryDirectory(prefix="ultron-readme-demo-") as folder:
        center = HealthCenter(Path(folder) / "health.json", lambda _notice: None)
        issue = center.record(
            "demo", "example.microphone", "Example microphone is unavailable",
            "Synthetic fixture only; no audio device was inspected.", "Unavailable",
        )
        print(f"  {AMBER}!{RESET} Health notice {issue['id']}: Example microphone is unavailable.")
        print(f"  Actions: ignore {issue['id']}  ·  dismiss {issue['id']}  ·  fix {issue['id']}")
        print(f"  {DIM}The notice is stored locally; no hardware was queried.{RESET}")
        pause(1.0)
        center.ignore(issue["id"])
        print(f"  {GREEN}✓{RESET} Issue {issue['id']} ignored. No code changed.\n")
    pause(0.8)

    print(f"{BLUE}REPAIR POLICY{RESET}")
    print("  Candidate patch → background full-harness rehearsal → owner reviews the diff")
    print("  Two separate confirmations → explicit apply. A test pass never auto-deploys.\n")
    pause(0.8)
    print(f"{DIM}Scripted README preview · offline · synthetic health event · no OS or web actions{RESET}")


if __name__ == "__main__":
    main()
