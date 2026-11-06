"""scripts/bench_sidecar.py — is the Go sidecar actually smaller and faster?

The language matrix claims one compiled component: a supervisor that outlives the
assistant, written in Go. That claim is only worth making if the numbers back it,
so this measures the four numbers that matter, against the Python watcher that
does the same job:

    size      the binary on disk, against the interpreter it replaces
    startup   milliseconds from exec to the first completed sweep
    memory    resident megabytes while it sits and watches
    latency   milliseconds from a real job ending to its event being on disk

Run it anywhere:  python scripts/bench_sidecar.py
It builds nothing. If the binary is missing it says how to build it and stops,
because a benchmark that silently downloads a toolchain is not a benchmark.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN_NAME = "watchd-windows.exe" if os.name == "nt" else "watchd-linux"
BINARY = ROOT / "sidecar" / "bin" / BIN_NAME


def rss_mb(pid: int) -> float:
    """Resident memory. Linux reads /proc; anything else says so honestly."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return float("nan")


def measure_startup(rounds: int = 5) -> float:
    """Median milliseconds from exec to one finished sweep (a fresh process each)."""
    samples = []
    for _ in range(rounds):
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            started = time.perf_counter()
            subprocess.run([str(BINARY), "-watch", "nothing-matches-this",
                            "-events", str(events), "-once"],
                           capture_output=True, check=False, timeout=60)
            samples.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(samples)


def measure_event_latency(poll_ms: int = 200) -> float:
    """Milliseconds from a real job ending to its event line being on disk."""
    with tempfile.TemporaryDirectory() as tmp:
        events = Path(tmp) / "events.jsonl"
        sidecar = subprocess.Popen([str(BINARY), "-watch", "sleep",
                                    "-events", str(events), "-poll", f"{poll_ms}ms"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.6)               # let it see the table once
            # A real job with a name the pattern matches. Spawning python and
            # watching "sleep" is how the first version of this reported nan.
            job = subprocess.Popen(["sleep", "0.4"] if os.name != "nt" else
                                   ["cmd", "/c", "timeout", "/t", "1", "/nobreak"])
            job.wait()
            ended = time.perf_counter()
            deadline = ended + 5.0
            while time.perf_counter() < deadline:
                if events.exists() and events.read_text().strip():
                    return (time.perf_counter() - ended) * 1000.0
                time.sleep(0.01)
            return float("nan")
        finally:
            sidecar.terminate()
            try:
                sidecar.wait(timeout=5)
            except Exception:
                sidecar.kill()


def measure_python_side() -> dict:
    """The Python watcher's equivalent costs, for comparison."""
    code = (
        "import time, json\n"
        "t0 = time.perf_counter()\n"
        "import psutil\n"
        "t1 = time.perf_counter()\n"
        "list(psutil.process_iter(['pid', 'name', 'create_time', 'cmdline', 'status']))\n"
        "t2 = time.perf_counter()\n"
        "import resource\n"
        "print(json.dumps({'import_ms': (t1-t0)*1000, 'sweep_ms': (t2-t1)*1000,"
        " 'rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        return {"import_ms": float("nan"), "sweep_ms": float("nan"), "rss_mb": float("nan")}


def main() -> int:
    if not BINARY.exists():
        print(f"missing {BINARY.relative_to(ROOT)}")
        print("Build it with:")
        print("  cd sidecar")
        print("  CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o bin/watchd-linux ./watchd")
        print("  CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath "
              "-ldflags='-s -w' -o bin/watchd-windows.exe ./watchd")
        return 2

    size_mb = BINARY.stat().st_size / (1024 * 1024)
    startup = measure_startup()
    latency = measure_event_latency()

    with tempfile.TemporaryDirectory() as tmp:
        sidecar = subprocess.Popen([str(BINARY), "-watch", "nothing-matches-this",
                                    "-events", str(Path(tmp) / "e.jsonl"), "-poll", "500ms"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        sidecar_rss = rss_mb(sidecar.pid)
        sidecar.terminate()
        try:
            sidecar.wait(timeout=5)
        except Exception:
            sidecar.kill()

    python = measure_python_side()

    print(f"machine: {platform.platform()}  python {sys.version.split()[0]}")
    print()
    print(f"{'':<26}{'Go sidecar':>16}{'Python watcher':>20}")
    print(f"{'binary / runtime size':<26}{size_mb:>14.1f} MB{'an interpreter + psutil':>20}")
    print(f"{'startup to first sweep':<26}{startup:>14.0f} ms"
          f"{python['import_ms'] + python['sweep_ms']:>17.0f} ms")
    print(f"{'resident memory':<26}{sidecar_rss:>14.1f} MB{python['rss_mb']:>17.1f} MB")
    print(f"{'event latency (200ms poll)':<26}{latency:>14.0f} ms{'same poll, same table':>20}")
    print()
    print("What this does NOT claim: the Go sidecar computes nothing faster. It wins")
    print("startup, footprint and survival — it keeps watching when the assistant")
    print("crashes. The other rows of the language matrix are unchanged and measured")
    print("in docs/LANGUAGE_MATRIX.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
