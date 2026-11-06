"""Microphone and speaker, driven the way the app drives them.

    python scripts/verify_audio.py
    python scripts/verify_audio.py --record 3 --play --save heard.wav

What it answers, in order: is sounddevice importable; how many devices are
there; does the default input open at the rate the app asks for; does a second
of audio actually arrive; does playback write; and what does the echo guard
measure from the device (the number `main.py` uses to decide when the room has
gone quiet).

Silence is not failure — a quiet room is silent. An exception, or an empty
buffer, is.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

results: list[dict] = []


def device_status(count: int) -> str:
    """Zero devices is a fact about the machine, so it is a SKIP, not a FAIL.

    A build server has no microphone. Reporting FAIL there says Ultron is broken
    on a machine that has nothing to be broken with — the same mistake the display
    check made in 1.2.11, fixed the same way. Devices that exist and then fail are
    still a FAIL, which is the case that matters on the owner's PC.
    """
    return "PASS" if count else "SKIP"


def record(name: str, status: str, detail: str = "") -> None:
    results.append({"check": name, "status": status, "detail": detail})
    print(f"  {status:4s}  {name}" + (f" — {detail}" if detail else ""))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="microphone and speaker")
    parser.add_argument("--record", type=float, default=2.0)
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--save", default="")
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)

    print(f"Audio on {platform.platform()}")
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:
        record("sounddevice imports", "FAIL", f"{type(exc).__name__}: {exc}")
        return finish(args.json)

    record("sounddevice imports", "PASS", f"PortAudio {sd.__version__}" if hasattr(sd, "__version__") else "")

    devices = sd.query_devices()
    ins = [d for d in devices if d.get("max_input_channels")]
    outs = [d for d in devices if d.get("max_output_channels")]
    record("input devices", device_status(len(ins)),
           (f"{len(ins)}: " + "; ".join(d["name"][:28] for d in ins[:3])) if ins
           else "no microphone on this machine — nothing to test here")
    record("output devices", "PASS" if outs else "SKIP",
           f"{len(outs)}: " + "; ".join(d["name"][:28] for d in outs[:3]))

    if not ins:
        return finish(args.json, "there is no microphone to test")

    info = sd.query_devices(kind="input")
    rate = int(info.get("default_samplerate") or 16000)
    frames_wanted = int(rate * args.record)
    started = __import__("time").monotonic()
    try:
        frames = sd.rec(frames_wanted, samplerate=rate, channels=1, dtype="int16")
        sd.wait()
    except Exception as exc:
        record("record a clip", "FAIL", f"{type(exc).__name__}: {exc}")
        return finish(args.json)
    took = __import__("time").monotonic() - started
    peak = int(np.abs(frames).max()) if frames.size else 0
    rms = float(np.sqrt(np.mean(frames.astype("float64") ** 2))) if frames.size else 0.0
    record("record a clip", "PASS" if frames.size else "FAIL",
           f"{frames.size} samples at {rate} Hz in {took:.2f}s, peak {peak}, "
           f"rms {rms:.1f} (whole numbers are digital silence)")
    if args.save and frames.size:
        with wave.open(args.save, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(frames.tobytes())
        record("clip saved", "PASS", args.save)

    # What main.py measures to decide the room has gone quiet.
    try:
        latency = sd.query_devices(kind="output").get("default_low_output_latency")
        record("output latency", "PASS" if latency is not None else "SKIP",
               f"{latency * 1000:.0f} ms" if latency else "not reported")
    except Exception as exc:
        record("output latency", "SKIP", str(exc))

    if args.play and outs:
        info_out = sd.query_devices(kind="output")
        out_rate = int(info_out.get("default_samplerate") or 24000)
        t = np.linspace(0, 0.6, int(out_rate * 0.6), endpoint=False)
        tone = (0.2 * np.sin(2 * np.pi * 440 * t) * 32767).astype("int16")
        try:
            sd.play(tone, samplerate=out_rate)
            sd.wait()
            record("play a tone", "PASS", "you should have heard 440 Hz for 0.6 s")
        except Exception as exc:
            record("play a tone", "FAIL", f"{type(exc).__name__}: {exc}")

    return finish(args.json)


def finish(report: str = "", extra: str = "") -> int:
    failed = [r for r in results if r["status"] == "FAIL"]
    passed = [r for r in results if r["status"] == "PASS"]
    print(f"\n  {len(passed)} passed, {len(failed)} failed"
          + (f" — {extra}" if extra else ""))
    if report:
        Path(report).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"  report: {report}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
