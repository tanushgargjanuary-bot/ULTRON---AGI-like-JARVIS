"""Pick a local model, fetch it, and prove it answers — without guessing.

The application already speaks to a local model: ``core/llm_client.py`` reads
``llm_provider``, ``llm_url`` and ``llm_model`` from ``config/api_keys.json`` and defaults to
Ollama on ``localhost:11434``. What was missing was a way to know, in one command, whether
that server is up, which models are on the disk, which one this machine can actually run, and
whether it answers in a sane time.

    python scripts/local_model.py             # what this machine can run, and what is installed
    python scripts/local_model.py pull        # fetch the recommended model through Ollama
    python scripts/local_model.py test        # ask it one question and time the answer
    python scripts/local_model.py write       # point the app at it (backs up the config first)

Nothing here is silent. Every step prints what it checked and what it changed, and ``write``
keeps a ``.bak`` of the file it touched.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
DEFAULT_URL = "http://localhost:11434"
TIMEOUT = 6

# One row per machine class. The model is the smallest that does the job well rather than the
# largest that fits: a 14B model on a laptop with no graphics card answers in minutes, and a
# slow answer is worse than a small correct one.
TIERS = (
    (4, "lfm2:1.2b", "LFM2 1.2B: under 900 MB, runs on a phone, two to three times faster "
                    "on a processor than a transformer of the same size."),
    (8, "llama3.2:3b", "3B: about 2 GB. Fine for chat and summaries, weak at code."),
    (16, "qwen2.5-coder:7b", "7B: about 5 GB. The smallest model worth using for code edits."),
    (32, "qwen2.5-coder:14b", "14B: better judgement, still runs on a plain desktop."),
    (10**4, "qwen2.5-coder:32b", "32 GB or more: the strongest model that still runs at home."),
)

# Three tiny jobs, chosen to show speed rather than score. A model that is quick here is
# worth giving work to; a model that is slow here is a model that will waste an evening.
BENCH_TASKS = (
    ("chat", "Reply with the single word: ready", ("ready",)),
    ("edit", "Fix this function so it adds. Reply with the corrected code only.\n\n"
             "def add(a, b):\n    return a - b", ("a + b",)),
    ("json", 'Reply with only this object: {"ok": true}', ('"ok"',)),
)


def total_memory_gb() -> float:
    """Physical memory in GB, or 0.0 when the machine will not say."""
    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        return 0.0


def graphics_memory_gb() -> float:
    """Largest NVIDIA card's memory in GB, or 0.0 when there is none."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        values = [float(line.strip()) / 1024 for line in out.stdout.splitlines() if line.strip()]
        return round(max(values), 1) if values else 0.0
    except Exception:
        return 0.0


def recommend(memory_gb: float, graphics_gb: float = 0.0) -> tuple[str, str]:
    """The model this machine should run, and one line saying why.

    Graphics memory is added to the budget because a model that fits in it runs ten to fifty
    times faster than the same model on the processor.
    """
    budget = max(memory_gb, 0.0) + max(graphics_gb, 0.0)
    for ceiling, model, why in TIERS:
        if budget <= ceiling:
            note = f"{budget:.0f} GB of memory" if budget else "memory unknown"
            if graphics_gb:
                note += f", {graphics_gb:.0f} GB on the graphics card"
            return model, f"{why} Chosen for {note}."
    return TIERS[-1][1], TIERS[-1][2]


def score_reply(expected: tuple, text: str) -> bool:
    """True when the answer contains any expected marker, ignoring case."""
    lowered = (text or "").lower()
    return any(marker.lower() in lowered for marker in expected)


def bench(url: str, model: str) -> list[dict]:
    """Run the three tiny jobs and report seconds and a pass mark for each."""
    results = []
    for name, prompt, expected in BENCH_TASKS:
        answer = ask(url, model, prompt)
        results.append({
            "task": name,
            "ok": bool(answer["ok"]) and score_reply(expected, answer["text"]),
            "seconds": answer["seconds"],
            "text": answer["text"],
            "error": answer["error"],
        })
    return results


def bench_lines(results: list[dict]) -> list[str]:
    """The bench as lines a person can read: one row per job, then the total."""
    lines = [f"  {'task':6} {'result':6} {'seconds':>7}"]
    for row in results:
        mark = "pass" if row["ok"] else "fail"
        lines.append(f"  {row['task']:6} {mark:6} {row['seconds']:>7}")
    total = round(sum(row["seconds"] for row in results), 2)
    passed = sum(1 for row in results if row["ok"])
    lines.append(f"  {passed} of {len(results)} passed, {total}s in total")
    return lines


def installed_models(url: str = DEFAULT_URL) -> list[str]:
    """Model names the local server has on disk. Empty list when the server is down."""
    try:
        response = requests.get(f"{url.rstrip('/')}/api/tags", timeout=TIMEOUT)
        response.raise_for_status()
        return [str(item.get("name", "")) for item in response.json().get("models", []) if item]
    except Exception:
        return []


def ask(url: str, model: str, prompt: str = "Reply with the single word: ready") -> dict:
    """Send one prompt and report what came back, and how long it took.

    The shape of the answer is fixed, so a caller can print it or test it without knowing
    anything about Ollama.
    """
    started = time.time()
    try:
        response = requests.post(
            f"{url.rstrip('/')}/api/chat",
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
            timeout=180,
        )
        response.raise_for_status()
        message = response.json().get("message", {})
        text = str(message.get("content", "")).strip()
        return {"ok": bool(text), "seconds": round(time.time() - started, 2), "text": text, "error": ""}
    except Exception as exc:
        return {"ok": False, "seconds": round(time.time() - started, 2), "text": "", "error": str(exc)}


def config_lines(url: str, model: str) -> dict:
    """The three keys the application reads for a local model."""
    return {"llm_provider": "ollama", "llm_url": url, "llm_model": model}


def write_config(path: Path, url: str, model: str) -> Path:
    """Write the three keys, keep a backup, and return where the backup went.

    An existing file is merged, not replaced: a key the owner pasted for a cloud provider must
    survive a switch to a local model.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        shutil.copy2(path, backup)
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    else:
        current = {}
    current.update(config_lines(url, model))
    path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return backup


def ollama_present() -> bool:
    """True when the ``ollama`` command exists on PATH."""
    return shutil.which("ollama") is not None


def _print_state(url: str) -> tuple[str, str]:
    memory, graphics = total_memory_gb(), graphics_memory_gb()
    model, why = recommend(memory, graphics)

    print("local model check")
    print(f"  memory: {memory or 'unknown'} GB   graphics: {graphics or 'none'} GB")
    print(f"  ollama on PATH: {'yes' if ollama_present() else 'no'}")
    print(f"  server at {url}: {'up' if installed_models(url) else 'down'}")

    present = installed_models(url)
    if present:
        print(f"  installed: {', '.join(present)}")
    else:
        print("  installed: none")

    print(f"  recommended: {model}")
    print(f"  because: {why}")
    return model, why


def _do_pull(model: str) -> int:
    """Download through Ollama. The only slow step, and the only one that uses the network."""
    if not ollama_present():
        print("\nOllama is not installed. Get it from https://ollama.com, then run this again.")
        return 1
    print(f"\npulling {model} — a few hundred megabytes for LFM2, several gigabytes for a 7B")
    return subprocess.run(["ollama", "pull", model]).returncode


def _do_test(url: str, model: str) -> int:
    """One question, timed. Proof the server and the model agree."""
    answer = ask(url, model)
    if answer["ok"]:
        print(f'\n{model} answered in {answer["seconds"]}s: "{answer["text"][:120]}"')
        return 0
    print(f"\n{model} did not answer: {answer['error']}")
    print("Is Ollama running, and is the model pulled?")
    return 1


def _do_bench(url: str, model: str) -> int:
    """Three tiny jobs. Speed first, quality second."""
    print(f"\nbenching {model} on three small jobs")
    results = bench(url, model)
    for line in bench_lines(results):
        print(line)
    if not any(row["ok"] for row in results):
        print("No job passed. Check that the model is pulled and the server is up.")
        return 1
    print("A model that passes two of three here can take one-file edits. Slower is not fatal;")
    print("failing every job is.")
    return 0


def _do_write(url: str, model: str, config: str, confirmed: bool) -> int:
    """Point the application at the model, keeping a backup."""
    target = Path(config)
    if not confirmed:
        print(f"\nabout to set llm_provider=ollama, llm_url={url}, llm_model={model}")
        print(f"in {target} (a .bak copy is kept)")
        if input("continue? [y/N] ").strip().lower() not in ("y", "yes"):
            print("nothing written")
            return 1
    backup = write_config(target, url, model)
    print(f"\nwrote {target}")
    if backup.exists():
        print(f"backup: {backup}")
    print("restart the application for the change to take effect.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Set up and check a local model.")
    parser.add_argument("command", nargs="?", default="check",
                        choices=["check", "pull", "test", "bench", "write"])
    parser.add_argument("--url", default=DEFAULT_URL, help="local server address")
    parser.add_argument("--model", default="", help="override the recommended model, e.g. lfm2:1.2b")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="config file to update")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args(argv)

    model, _why = _print_state(args.url)
    model = args.model or model

    if args.command == "check":
        print("\nnext: python scripts/local_model.py pull")
        return 0
    if args.command == "pull":
        return _do_pull(model)
    if args.command == "test":
        return _do_test(args.url, model)
    if args.command == "bench":
        return _do_bench(args.url, model)
    return _do_write(args.url, model, args.config, args.yes)


if __name__ == "__main__":
    sys.exit(main())
