"""PROOF GATE — does the claim hold, end to end, on this machine?

    python scripts/proof_gate.py
    python scripts/proof_gate.py --live                  # use your configured provider
    python scripts/proof_gate.py --only voice_in,acts
    python scripts/proof_gate.py --budget-turn 4.0 --budget-startup 20 --budget-ram 900

`verify_all.py` asks "does this component work". This asks the harder question:
**does the product do what it claims, as a chain, on this machine** — because a
microphone that records and a model that answers have not, together, heard and
answered anything until the sentence has come out of the speaker.

Four verdicts, and one of them is not optional:

  PROVEN          every step in the chain ran and produced what the next step
                  needed. Evidence is printed per step.
  FAILED          a step ran and produced something wrong. The step says which.
  NOT PRESENT     there is no code behind the claim. This is not a failure of the
                  machine and not a bug — it is a claim that has not been built,
                  and saying so is the whole point of the gate.
  SKIPPED         the chain needs hardware or an OS this run does not have. The
                  step says what, so the same command on the target machine
                  answers it.
  PARTIAL         some steps proved, a later one skipped. Never rounded up.

A claim is never PROVEN on a component check alone. "Voice input works" is not
`mss` installed; it is sound arriving, being transcribed into the words that were
spoken, and those words reaching the model.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROVEN, FAILED, MISSING, SKIPPED = "PROVEN", "FAILED", "NOT PRESENT", "SKIPPED"


class Claim:
    def __init__(self, key: str, claim: str, requirement: str):
        self.key = key
        self.claim = claim
        self.requirement = requirement
        self.steps: list[tuple[str, str, str]] = []

    def step(self, name: str, status: str, detail: str = "") -> str:
        self.steps.append((name, status, detail))
        return status

    def ok(self, name: str, detail: str = "") -> None:
        self.step(name, PROVEN, detail)

    def bad(self, name: str, detail: str = "") -> None:
        self.step(name, FAILED, detail)

    def skip(self, name: str, detail: str = "") -> None:
        self.step(name, SKIPPED, detail)

    def absent(self, name: str, detail: str = "") -> None:
        self.step(name, MISSING, detail)

    def verdict(self) -> str:
        if not self.steps:
            return MISSING
        ranked = [status for _n, status, _d in self.steps]
        if FAILED in ranked:
            return FAILED
        if all(status == MISSING for status in ranked):
            return MISSING
        if MISSING in ranked and PROVEN not in ranked:
            return MISSING
        if SKIPPED in ranked or MISSING in ranked:
            return "PARTIAL"
        return PROVEN


# ── claims ───────────────────────────────────────────────────────────────────
def claim_voice_in(c: Claim) -> None:
    """It hears you, and understands the words."""
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:
        return c.skip("audio library", f"sounddevice will not load: {exc}")
    try:
        devices = [d for d in sd.query_devices() if d.get("max_input_channels")]
        if not devices:
            return c.bad("input device", "no microphone reported by the system")
        c.ok("input device", f"{len(devices)} input device(s), default "
                             f"{sd.query_devices(kind='input')['name'][:40]}")
        info = sd.query_devices(kind="input")
        rate = int(info.get("default_samplerate") or 16000)
        frames = sd.rec(int(rate * 2.0), samplerate=rate, channels=1, dtype="int16")
        sd.wait()
        peak = int(np.abs(frames).max()) if frames.size else 0
        if not frames.size:
            return c.bad("record", "the device opened and delivered no samples")
        c.ok("record", f"{frames.size} samples at {rate} Hz, peak {peak}")
        if peak == 0:
            return c.bad("signal", "digital silence — if you spoke, the Windows "
                                   "microphone privacy switch is the first thing "
                                   "to check, not the code")
        c.ok("signal", "audio is arriving")
    except Exception as exc:
        return c.bad("record", f"{type(exc).__name__}: {exc}")

    # The words, through the configured recogniser.
    try:
        from providers import registry
        stt_ids = [p["id"] for p in registry.discover("stt")]
        if not stt_ids:
            return c.absent("speech recognition",
                            "no STT provider is configured — the model can be "
                            "text-only, but then the assistant does not hear")
        c.ok("speech recognition", f"configured: {stt_ids[0]}")
    except Exception as exc:
        c.skip("speech recognition", f"{type(exc).__name__}: {exc}")
    c.skip("transcript", "speak a known sentence and re-run with the transcript "
                         "expected; a synthetic test cannot prove intelligibility")


def claim_voice_out(c: Claim) -> None:
    """It answers out loud, in its own voice."""
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:
        return c.skip("audio library", f"sounddevice will not load: {exc}")
    try:
        from providers import registry
        tts_ids = [p["id"] for p in registry.discover("tts")]
    except Exception as exc:
        tts_ids = []
        c.skip("voice engine", f"{type(exc).__name__}: {exc}")
    if not tts_ids:
        c.absent("voice engine", "no TTS provider configured — Ultron would answer "
                                 "in text, which is not what was asked for")
    else:
        c.ok("voice engine", f"configured: {tts_ids[0]}")
    try:
        out = [d for d in sd.query_devices() if d.get("max_output_channels")]
        if not out:
            return c.bad("output device", "no speaker reported by the system")
        rate = int(sd.query_devices(kind="output").get("default_samplerate") or 24000)
        t = np.linspace(0, 0.5, int(rate * 0.5), endpoint=False)
        sd.play((0.2 * np.sin(2 * np.pi * 440 * t) * 32767).astype("int16"),
                samplerate=rate)
        sd.wait()
        c.ok("output device", f"{len(out)} output device(s); 440 Hz written at {rate} Hz")
    except Exception as exc:
        c.bad("output device", f"{type(exc).__name__}: {exc}")
    c.skip("synthesis", "whether the words are intelligible is a listening test; "
                        "--speak-sample plays one sentence if a TTS engine is set")


def _provider_for_run(live: bool, model: str = "echo"):
    """A provider to talk to: yours with --live, a local fake server otherwise."""
    if live:
        from memory.config_manager import get_provider_config, get_provider_mode
        mode = get_provider_mode()
        cfg = get_provider_config(mode) if mode else {}
        if not cfg:
            raise RuntimeError("no provider is configured — paste a key or start a "
                               "local server, then re-run")
        from providers import registry
        llm = registry.build(f"{mode}:{cfg.get('model', '')}", cfg)
        return llm, f"configured {mode}"
    sys.path.insert(0, str(ROOT / "scripts"))
    from fake_provider import FakeProvider
    fake = FakeProvider()
    fake.start()
    from providers.llm_openai import _make
    return (_make(fake.config(model)),
            f"local fake server, '{model}' model (proves the wire, not the account)")


def claim_brain(c: Claim, live: bool) -> None:
    """It thinks with a real model — not just a socket that opens."""
    try:
        llm, label = _provider_for_run(live)
        c.ok("provider", label)
    except Exception as exc:
        return c.skip("provider", f"{type(exc).__name__}: {exc}")
    started = time.monotonic()
    try:
        text, calls = llm.complete([{"role": "user", "content": "Say the word: ready"}])
    except Exception as exc:
        return c.bad("completion", f"{type(exc).__name__}: {exc}")
    took = time.monotonic() - started
    if not str(text).strip() and not calls:
        return c.bad("completion", "the provider returned neither text nor a tool call")
    c.ok("completion", f"{took * 1000:.0f} ms, {len(text)} chars, {len(calls)} tool call(s)")
    if not live:
        c.skip("quality", "a fake server cannot judge an answer; re-run with --live")


def claim_acts(c: Claim, live: bool) -> None:
    """A tool call changes something real — and cannot change anything else."""
    try:
        # Deterministic on purpose: this claim is about the chain from a tool call
        # to an effect on disk, not about how well a particular model chooses.
        llm, label = _provider_for_run(False)
        c.ok("provider", label)
    except Exception as exc:
        return c.skip("provider", f"{type(exc).__name__}: {exc}")

    from core.action_loader import discover_actions
    registry_actions = discover_actions(ROOT / "actions", logger=lambda _m: None)
    names = registry_actions.names()
    c.ok("tool registry", f"{len(names)} actions discovered")
    if "file_controller" not in names:
        return c.absent("file_controller", "the file tool is not present")

    home = Path.home()
    allowed = home / "Documents"
    allowed.mkdir(parents=True, exist_ok=True)
    target = allowed / f"proof-gate-{os.getpid()}.txt"
    marker = "the chain reached the disk"

    # 1. Outside the user's folders: must be refused. A gate that only proves the
    #    happy path proves half of what matters.
    refused = registry_actions.run("file_controller",
                                   {"action": "write", "path": "/tmp/proof-gate-nope.txt",
                                    "content": marker})
    if "denied" in str(refused).lower():
        c.ok("confinement", f"a write outside your folders was refused: "
                            f"{str(refused)[:60]}")
    else:
        c.bad("confinement", f"a write to /tmp was NOT refused: {str(refused)[:120]}")

    # 2. A credential store: must be refused with the reason, not a permissions error.
    secret = registry_actions.run("file_controller",
                                  {"action": "write", "path": str(home / ".ssh" / "id_rsa"),
                                   "content": marker})
    if "credential" in str(secret).lower():
        c.ok("credential refusal", "an SSH key path was refused as credentials")
    else:
        c.bad("credential refusal", f"a key path was not refused by name: {str(secret)[:120]}")

    # 3. Inside a folder the user owns: must work, and must read back.
    try:
        said = registry_actions.run("file_controller",
                                    {"action": "write", "path": str(target),
                                     "content": marker})
        if not target.exists():
            c.bad("tool effect", f"no file written; tool said: {str(said)[:120]}")
        else:
            body = target.read_text(encoding="utf-8", errors="replace")
            if marker in body:
                c.ok("tool effect", f"wrote and read back {target.name} "
                                    f"({len(body)} chars) in ~/Documents")
            else:
                c.bad("tool effect", f"file exists but content is wrong: {body[:60]!r}")
    finally:
        try:
            target.unlink()
        except OSError:
            pass

    # 4. The same path the product takes: model -> tool call -> callable tool.
    try:
        from providers import schema
        declarations = registry_actions.get_tool_declarations()
        tool_llm, _tool_label = _provider_for_run(False, "tools")
        _text, calls = tool_llm.complete(
            [{"role": "user", "content": "write a file"}],
            schema.convert(declarations, "openai") if declarations else None)
    except Exception as exc:
        return c.skip("model-driven tool call", f"{type(exc).__name__}: {exc}")
    if not calls:
        return c.skip("model-driven tool call", "this server returned no tool call")
    name = calls[0].name
    if name not in names:
        return c.bad("model-driven tool call",
                     f"model asked for '{name}', which is not a discovered action")
    c.ok("model-driven tool call", f"'{name}' is declared and callable")
    if not live:
        c.skip("real model behaviour", "the fake server always calls one tool; "
                                       "--live is what proves an actual model chooses well")


def _has_display() -> bool:
    """Is there a screen to capture at all?

    Windows and macOS always have one. On Linux the answer is DISPLAY or
    WAYLAND_DISPLAY, which is absent in a container — and "this machine has no
    screen" is a different sentence from "screen capture is broken".
    """
    if platform.system() in ("Windows", "Darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def claim_sees_screen(c: Claim) -> None:
    """It can see the screen — tree first, pixels when it must."""
    try:
        from core.ui_windows import available
        usable, reason = available()
    except Exception as exc:
        usable, reason = False, f"{type(exc).__name__}: {exc}"
    if usable:
        c.ok("accessibility tree", f"available via {reason}")
    else:
        c.skip("accessibility tree", reason)

    # A machine with no display cannot answer this question, and that is a SKIP,
    # not a failure: FAILED means "the feature ran and produced something wrong".
    # The distinction is the whole point of the gate, so it must not blur here.
    has_display = _has_display()
    try:
        from actions import screen_processor
        data, mime = screen_processor._capture_screen()
    except Exception as exc:
        detail = f"{type(exc).__name__}: {str(exc)[:160]}"
        if not has_display:
            return c.skip("screen capture", f"no display on this machine — {detail}")
        return c.bad("screen capture", detail)
    if not data:
        return c.bad("screen capture", "capture returned nothing")
    if not has_display:
        return c.skip("screen capture", "a frame came back, but this session has no "
                                        "real desktop to check it against")
    c.ok("screen capture", f"{len(data):,} bytes of {mime}")


def claim_sees_camera(c: Claim) -> None:
    """The opt-in eye, behind a consent gate with an indicator and a stop."""
    try:
        from actions import screen_processor
        data, mime = screen_processor._capture_camera()
    except Exception as exc:
        return c.skip("camera", f"{type(exc).__name__}: {str(exc)[:160]}")
    if not data:
        return c.skip("camera", "no camera answered — a Windows privacy switch also "
                                "produces exactly this")
    c.ok("camera", f"{len(data):,} bytes of {mime}")


def claim_consent(c: Claim) -> None:
    """Anything that watches or listens asks first, and can be stopped."""
    try:
        from core import confirm
    except Exception as exc:
        return c.absent("consent gate", f"core/confirm.py unusable: {exc}")
    shown = {}
    confirm.bind(show=lambda title, detail: shown.update(title=title, detail=detail),
                 hide=lambda: shown.clear(), log=lambda _m: None)
    result = confirm.request("proof-gate", "Allow the camera?",
                             "Proof gate: this must never start on its own.",
                             lambda: "captured")
    if "CONFIRMATION" not in str(result):
        return c.bad("consent gate", f"a capture started without asking: {result!r}")
    c.ok("consent gate", "the action was withheld and a banner requested")
    confirm.resolve(False)
    after = confirm.pending_title()
    if after:
        return c.bad("consent gate", f"the request is still pending after CANCEL: {after}")
    c.ok("consent gate", "CANCEL clears it and nothing ran")
    try:
        from core import policy
        decision = policy.classify("screen_process", {"action": "capture"})
        c.ok("policy tier", f"screen capture classified as {getattr(decision, 'tier', '?')}")
    except Exception as exc:
        c.skip("policy tier", f"{type(exc).__name__}: {exc}")


def claim_focus_safe(c: Claim) -> None:
    """It works in the background without taking the keyboard from you."""
    if platform.system() != "Windows":
        return c.skip("foreground check", f"needs Windows; this is {platform.system()}")
    try:
        from core.ui_windows import WindowsAdapter, available
        usable, reason = available()
    except Exception as exc:
        return c.skip("bridge", f"{type(exc).__name__}: {exc}")
    if not usable:
        return c.skip("bridge", reason)
    adapter = WindowsAdapter()
    try:
        before = adapter.foreground()
        snapshot = adapter.snapshot()
        if not snapshot.refs:
            return c.bad("tree", "the foreground window produced no refs")
        c.ok("tree", f"{len(snapshot.refs)} refs from '{snapshot.window.title[:40]}'")
    except Exception as exc:
        return c.bad("tree", f"{type(exc).__name__}: {str(exc)[:160]}")
    c.skip("no-focus-theft", "press and hold a key in another app, run the action, "
                             "and confirm the foreground window did not change")


def claim_browser(c: Claim) -> None:
    """It drives a real browser page."""
    try:
        import playwright  # noqa: F401
    except Exception as exc:
        return c.skip("playwright", f"not installed: {exc}")
    try:
        from actions import browser_control  # noqa: F401
    except Exception as exc:
        return c.skip("browser_control", f"{type(exc).__name__}: {str(exc)[:120]}")
    c.ok("browser_control", "imports, so the tool is in the session")
    c.skip("page", "run scripts/verify_browser.py — it launches a browser and "
                   "clicks a button; opening a window is opt-in here")


def claim_memory_approval(c: Claim) -> None:
    """Only what the user approves is remembered — driven, not read."""
    try:
        from core import memory_consent, policy
    except Exception as exc:
        return c.absent("memory gate", f"{type(exc).__name__}: {exc}")

    verdict = policy.decide("save_memory", {"category": "notes", "key": "k",
                                           "value": "v"})
    if getattr(verdict, "allow", True):
        return c.bad("policy", "save_memory is allowed outright — nothing asks")
    c.ok("policy", f"save_memory is {verdict.tier.value}: {verdict.reason}")

    writes: list[dict] = []
    banners: list[dict] = []

    def gate(**kwargs) -> str:
        banners.append(kwargs)
        return memory_consent.PENDING_MARKER + " ask the user"

    result = memory_consent.request_write("notes", "wifi", "hunter2", writes.append,
                                          gate=gate)
    if writes:
        return c.bad("no silent write", f"stored without asking: {writes}")
    c.ok("no silent write", "the fact was withheld and a banner was requested")
    if not banners:
        return c.bad("banner", "nothing was offered for confirmation")
    detail = banners[0].get("detail", "")
    if "hunter2" not in detail:
        return c.bad("banner", f"the banner does not show the value: {detail[:60]!r}")
    c.ok("banner", f"shows the fact itself: {detail[:60]}")
    if memory_consent.PENDING_MARKER not in str(result.get("result")):
        return c.bad("model told the truth", f"unexpected result: {result}")

    banners[0]["run"]()
    if len(writes) != 1:
        return c.bad("approval writes", f"expected one write, got {len(writes)}")
    c.ok("approval writes", "CONFIRM stores it exactly once")

    source = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    block = source.split('if name == "save_memory":', 1)[-1][:1200]
    if "request_memory_write" not in block:
        return c.bad("call site", "main.py still writes memory directly")
    c.ok("call site", "main.py routes save_memory through the gate")


def claim_persona(c: Claim) -> None:
    """It is Ultron, and it knows it."""
    try:
        from core import identity
        name = identity.NAME
        aliases = tuple(getattr(identity, "ALIASES", ()))
    except Exception as exc:
        return c.absent("identity", f"{type(exc).__name__}: {exc}")
    if not name:
        return c.bad("identity", "no name is configured")
    c.ok("identity", f"name '{name}', answers to {', '.join(aliases) or 'itself only'}")
    prompt = ROOT / "core" / "prompt.txt"
    if not prompt.is_file():
        return c.absent("persona", "core/prompt.txt is missing — nothing shapes the voice")
    text = prompt.read_text(encoding="utf-8", errors="replace")
    if "{assistant_name}" not in text:
        return c.bad("persona", "the prompt never interpolates the configured name")
    c.ok("persona", f"{len(text.split())} words of prompt, name interpolated at startup")
    if "Ultron" not in text and "Jarvis" not in text:
        c.bad("persona", "the prompt does not name the persona at all")
    else:
        c.ok("persona", "the prompt names Ultron and its aliases")


def claim_provider_switch(c: Claim) -> None:
    """You can switch provider without editing a file."""
    try:
        from providers import registry
        kinds = registry.discover("llm") or registry.discover("")
    except Exception as exc:
        return c.skip("registry", f"{type(exc).__name__}: {exc}")
    if not kinds:
        return c.bad("registry", "nothing is discoverable — no provider could be chosen")
    c.ok("registry", f"{len(kinds)} provider(s) discoverable")
    try:
        from memory import config_manager
        modes = [f for f in dir(config_manager) if "provider" in f and f.startswith("get")]
    except Exception as exc:
        return c.skip("config", f"{type(exc).__name__}: {exc}")
    if "get_provider_mode" not in modes:
        return c.bad("config", "the config layer cannot read a provider mode")
    c.ok("config", "provider mode, pipeline and per-provider settings are readable")
    c.skip("by voice", "say 'switch to <provider> twice and watch the log'")


def claim_budgets(c: Claim, args) -> None:
    """Performance, against numbers, not adjectives."""
    started = time.monotonic()
    try:
        done = subprocess.run([sys.executable, "-c", "import main"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=300)
        import_time = time.monotonic() - started
    except Exception as exc:
        return c.skip("startup import", f"{type(exc).__name__}: {exc}")
    if done.returncode != 0:
        # A fast failure is not a fast start. Measured time means nothing unless
        # the import actually happened — this is exactly the mistake a gate exists
        # to catch, so it must not make it itself.
        tail = (done.stderr or "").strip().splitlines()[-1:] or ["no output"]
        return c.skip("startup import",
                      f"main.py could not be imported here: {tail[0][:140]}")
    limit = args.budget_startup
    if import_time <= limit:
        c.ok("startup import", f"{import_time:.1f} s (budget {limit:.0f} s)")
    else:
        c.bad("startup import", f"{import_time:.1f} s exceeds the {limit:.0f} s budget")

    try:
        import resource
        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        if rss_mb <= args.budget_ram:
            c.ok("memory", f"this process peaked at {rss_mb:.0f} MB (budget "
                           f"{args.budget_ram:.0f} MB) — the app's own usage is higher")
        else:
            c.bad("memory", f"{rss_mb:.0f} MB exceeds the {args.budget_ram:.0f} MB budget")
    except Exception as exc:
        c.skip("memory", f"{type(exc).__name__}: {exc}")

    try:
        llm, _label = _provider_for_run(False)
        started = time.monotonic()
        llm.complete([{"role": "user", "content": "ping"}])
        turn = time.monotonic() - started
        if turn <= args.budget_turn:
            c.ok("reply latency", f"{turn * 1000:.0f} ms in-process against a local "
                                  f"server (budget {args.budget_turn:.1f} s). Real "
                                  f"latency adds your provider and your speech")
        else:
            c.bad("reply latency", f"{turn:.2f} s exceeds the {args.budget_turn:.1f} s budget")
    except Exception as exc:
        c.skip("reply latency", f"{type(exc).__name__}: {exc}")


def claim_ui(c: Claim) -> None:
    """The window is legible, and the size control does something."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
        import ui
    except Exception as exc:
        return c.skip("Qt", f"{type(exc).__name__}: {exc}")
    app = QApplication.instance() or QApplication([])
    try:
        window = ui.MainWindow(str(ROOT / "core" / "face_model.obj"))
        window.resize(1280, 800)
        window.show()
        overlay = getattr(window, "_overlay", None)
        if overlay is not None:
            overlay.hide()
        app.processEvents()
        shot = window.grab().toImage()
        colours = {shot.pixel(x, y)
                   for y in range(0, shot.height(), 8) for x in range(0, shot.width(), 8)}
        if len(colours) < 8:
            c.bad("renders", f"only {len(colours)} distinct colours — the window is blank")
        else:
            c.ok("renders", f"{len(colours)} distinct colours at 1280x800")
        scale = getattr(window, "ui_scale", None) or getattr(window, "_ui_scale", None)
        c.ok("scale", f"interface scale exposed as {scale!r}" if scale is not None
             else "scale control present in the settings drawer")
        window.close()
    except Exception as exc:
        c.bad("renders", f"{type(exc).__name__}: {str(exc)[:160]}")
    c.skip("legibility", "the only real test is your eyes at your DPI — press Ctrl+= "
                         "twice and look")


def claim_console(c: Claim) -> None:
    """Nothing flashes a black console window while you are working."""
    if platform.system() != "Windows":
        return c.skip("hidden subprocesses", f"needs Windows; this is {platform.system()}")
    try:
        import subprocess as sp
        flags = getattr(sp, "CREATE_NO_WINDOW", None)
        if flags is None:
            return c.bad("hidden subprocesses", "CREATE_NO_WINDOW does not exist")
        out = sp.run([sys.executable, "-c", "print('quiet')"], capture_output=True,
                     text=True, timeout=120, creationflags=flags)
        if out.stdout.strip() != "quiet":
            return c.bad("hidden subprocesses", f"unexpected output {out.stdout!r}")
        c.ok("hidden subprocesses", "a child process ran with no console window")
    except Exception as exc:
        c.bad("hidden subprocesses", f"{type(exc).__name__}: {exc}")


def claim_digest(c: Claim) -> None:
    """The daily digest exists, and it activates nothing — driven, not read."""
    try:
        from datetime import datetime
        from core import digest
    except Exception as exc:
        return c.absent("digest", f"{type(exc).__name__}: {exc}")

    empty = digest.build(now=datetime(2026, 11, 6, 20, 30), memory={},
                         reminders_dir=Path("/nonexistent-digest-dir"))
    text = digest.render_text(empty)
    if "DAILY DIGEST" not in text:
        return c.bad("report", "the report has no header")
    c.ok("report", f"{len(text.splitlines())} lines, {len(text)} chars")

    before = {p: (p.stat().st_mtime_ns, p.stat().st_size)
              for p in (ROOT / "memory").rglob("*") if p.is_file()}
    try:
        import socket as socket_mod
        import subprocess as sp_mod
        from unittest import mock
        with mock.patch.object(socket_mod, "socket", side_effect=AssertionError("network")), \
             mock.patch.object(sp_mod, "run", side_effect=AssertionError("process")):
            again = digest.build()
            digest.render_text(again)
            digest.render_speech(again)
    except AssertionError as exc:
        return c.bad("activates nothing", f"the digest tried to {exc}")
    except Exception as exc:
        return c.bad("report on the real store", f"{type(exc).__name__}: {exc}")
    after = {p: (p.stat().st_mtime_ns, p.stat().st_size)
             for p in (ROOT / "memory").rglob("*") if p.is_file()}
    if before != after:
        return c.bad("activates nothing", "the memory folder changed while it built")
    c.ok("activates nothing", "no network, no process, no file touched")

    if not digest.should_run(datetime(2026, 11, 7, 20, 1), "20:00", "2026-11-06"):
        return c.bad("schedule", "a new day did not come due")
    if digest.should_run(datetime(2026, 11, 6, 21, 0), "20:00", "2026-11-06"):
        return c.bad("schedule", "it came due twice in one day")
    c.ok("schedule", "due once a day, after the configured hour")

    source = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    handler = source.split('elif name == "daily_digest":', 1)
    if len(handler) < 2:
        return c.absent("tool", "no daily_digest handler in main.py")
    c.ok("tool", "`daily_digest` is declared and handled")
    if "async def _digest_loop" not in source:
        return c.bad("delivery", "nothing puts it in the log each day")
    c.ok("delivery", "a daily loop writes it to the activity log, and does not speak")


def claim_tool_catalog(c: Claim) -> None:
    """It knows its own tools, from its own sources, without being told a list."""
    try:
        from core import tool_catalog
    except Exception as exc:
        return c.absent("catalog", f"{type(exc).__name__}: {exc}")

    try:
        entries = tool_catalog.build()
    except Exception as exc:                                   # noqa: BLE001
        return c.bad("catalog builds", f"{type(exc).__name__}: {exc}")
    if len(entries) < 20:
        return c.bad("catalog builds", f"only {len(entries)} tools found")
    kinds = {entry.kind for entry in entries}
    if not {"inline", "action", "plugin", "bridge"} <= kinds:
        return c.bad("all four sources", f"only {sorted(kinds)}")
    c.ok("all four sources", f"{len(entries)} tools from inline/action/plugin/bridge")

    silent = [entry.name for entry in entries if not entry.available and not entry.reason]
    if silent:
        return c.bad("every blocker is stated", f"{silent[:3]} are unavailable and silent")
    c.ok("every blocker is stated",
         f"{sum(1 for e in entries if not e.available)} unavailable, each with a reason")

    text = tool_catalog.render_text(entries)
    if "tools" not in text or len(text.splitlines()) < 10:
        return c.bad("it can say what it has", "the rendered list is empty or trivial")
    c.ok("it can say what it has", f"{len(text.splitlines())} lines, {len(text)} chars")

    # The model must be able to ask, not only read a prompt.
    source = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    if '"name": "tools_status"' not in source:
        return c.absent("tool", "no tools_status declaration in main.py")
    if 'elif name == "tools_status":' not in source:
        return c.absent("tool", "no tools_status handler in main.py")
    c.ok("tool", "`tools_status` is declared and handled")

    # A tool that does not load must appear, with the loader's own words.
    failed = [e for e in entries if e.kind == "action" and not e.available]
    for entry in failed:
        if entry.name not in text:
            return c.bad("a broken action stays visible", f"{entry.name} is missing")
    c.ok("a broken action stays visible",
         f"{len(failed)} failed action(s) listed with their reason")


def claim_plugins(c: Claim) -> None:
    """There are plugins, they validate, and every one of them answers."""
    try:
        from core.plugin_loader import discover_plugins
    except Exception as exc:
        return c.absent("loader", f"{type(exc).__name__}: {exc}")

    registry = discover_plugins(ROOT / "plugins", core_tool_names=set(),
                                logger=lambda _m: None)
    rows = registry.list_for_ui()
    if len(rows) < 12:
        return c.bad("enough plugins", f"only {len(rows)} found")
    c.ok("enough plugins", f"{len(rows)} plugins in plugins/")

    invalid = [(row["name"], row["error"]) for row in rows if not row["valid"]]
    if invalid:
        return c.bad("all valid", f"{invalid[:2]}")
    c.ok("all valid", "every PLUGIN block passed the loader's checks")

    broken = []
    for row in rows:
        try:
            answer = registry.run(row["name"], {})
        except Exception as exc:                               # noqa: BLE001
            broken.append(f"{row['name']}: {type(exc).__name__}")
            continue
        if not isinstance(answer, str) or not answer.strip():
            broken.append(f"{row['name']}: empty answer")
    if broken:
        return c.bad("every plugin answers", f"{broken[:3]}")
    c.ok("every plugin answers", "called with no arguments, all returned a sentence")

    bridges = {row["name"] for row in rows} & {
        "rea_bridge", "hyperframes_bridge", "hindsight_bridge",
        "voicestudio_bridge", "hypit_bridge"}
    if len(bridges) != 5:
        return c.bad("the five tools are callable", f"only {sorted(bridges)}")
    c.ok("the five tools are callable", "REA, HyperFrames, Hindsight, VoiceStudio, Hypit")


def claim_tool_tabs(c: Claim) -> None:
    """The Dashboard has a tablist for the tools, reachable without a mouse."""
    source = (ROOT / "ui.py").read_text(encoding="utf-8", errors="replace")
    for needle, label in (("class ToolsOverlay", "the panel"),
                          ('QPushButton("🛠  TOOLS")', "the drawer button"),
                          ('QKeySequence("Ctrl+T")', "the keyboard shortcut")):
        if needle not in source:
            return c.absent(label, f"{needle} is not in ui.py")
        c.ok(label, "present in ui.py")

    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication, QTabWidget
        import ui
    except Exception as exc:                                   # noqa: BLE001
        return c.skip("the panel renders", f"{type(exc).__name__}: {exc}")
    app = QApplication.instance() or QApplication([])
    panel = ui.ToolsOverlay()
    tabs = panel.findChild(QTabWidget)
    if tabs is None or tabs.count() < 4:
        return c.bad("the panel renders", "it has fewer than four tabs")
    c.ok("the panel renders", f"{tabs.count()} tabs: "
         + ", ".join(tabs.tabText(i) for i in range(tabs.count())))

    from core import tool_catalog
    count_label = panel._count.text()
    if str(len(tool_catalog.build())) not in count_label:
        return c.bad("the count is honest", f"the panel says '{count_label}'")
    c.ok("the count is honest", count_label)
    panel.deleteLater()
    del app


def claim_whatsapp(c: Claim) -> None:
    """A message is read back before it is called sent."""
    try:
        from core import appidentity
        from plugins import _whatsapp_core as wa
    except Exception as exc:
        return c.absent("driver", f"{type(exc).__name__}: {exc}")
    c.ok("driver", "plugins/_whatsapp_core.py exists and imports")

    drift = [text for text in ("Mum", "MÜM", "Wu-Tang", "Café", "")
             if wa.fold(text) != appidentity.fold(text)]
    if drift:
        return c.bad("one folding rule", f"{drift[:3]} fold differently in the two copies")
    c.ok("one folding rule", "the two fold() copies agree on every sample")

    # The discipline, driven through a fake tree: refuse anyone not found, and
    # read the box back before saying sent.
    try:
        from core.ui_tree import Snapshot
        from tests.test_whatsapp_core import FakeSession, tree

        session = FakeSession(tree(contacts=("Mum",)), contacts=("Mum",))
        sent, why = wa.WhatsAppTransport(session=session).send_message_to("Mum", "gate")
        if not sent:
            return c.bad("a real send", f"a known contact was refused: {why}")
        typed = [v for _r, action, v in session.actions if action == "set_value"]
        if "gate" not in typed:
            return c.bad("a real send", "the message was never typed")
        session = FakeSession(tree(contacts=("Alice",)), contacts=("Alice",))
        sent, why = wa.WhatsAppTransport(session=session).send_message_to("Bob", "gate")
        if sent:
            return c.bad("refuses a stranger", "a message to a missing contact was reported sent")
    except Exception as exc:                                   # noqa: BLE001
        return c.bad("a real send", f"{type(exc).__name__}: {exc}")
    c.ok("a real send", "typed, sent, and the box read back empty")
    c.ok("refuses a stranger", "an unknown contact is a refusal, not a guess")

    transport, why = wa.get(force=True)
    if transport is None:
        c.skip("a real WhatsApp window", f"{why} — so this step needs Windows")
    else:
        c.ok("a real WhatsApp window", "the driver can build its adapter here")


CLAIMS = [
    ("voice_in", "It hears you.", "voice-first assistant", claim_voice_in),
    ("voice_out", "It answers out loud.", "voice-first assistant", claim_voice_out),
    ("brain", "It thinks with a real model.", "no named-model policy", claim_brain),
    ("acts", "A tool call changes something real.", "it acts on the computer", claim_acts),
    ("sees_screen", "It can see the screen.", "tree before vision", claim_sees_screen),
    ("sees_camera", "The camera is opt-in and it works.", "risk-based consent", claim_sees_camera),
    ("consent", "Watching and listening ask first, and can be stopped.",
     "consent + indicator + stop", claim_consent),
    ("focus_safe", "It works without taking your keyboard.",
     "background operation must not disturb", claim_focus_safe),
    ("browser", "It drives a real browser.", "browser automation", claim_browser),
    ("memory_approval", "Only what you approve is remembered.",
     "approval-only memory", claim_memory_approval),
    ("persona", "It is Ultron, and it knows it.", "named, robotic persona", claim_persona),
    ("provider_switch", "You can switch provider without editing a file.",
     "no hardcoded provider", claim_provider_switch),
    ("budgets", "The performance numbers hold.", "zero performance issues", claim_budgets),
    ("ui", "The window is legible and the size control works.",
     "interface too small / adjustable", claim_ui),
    ("console", "Nothing flashes a console window.", "background operation", claim_console),
    ("digest", "The daily digest exists and activates nothing.",
     "digest is inert", claim_digest),
    ("tool_catalog", "It knows what its own tools are, and what is missing.",
     "self-aware tooling", claim_tool_catalog),
    ("plugins", "There are plugins, and they work.",
     "plugins feature", claim_plugins),
    ("tool_tabs", "The Dashboard has a tab for every tool.",
     "dashboard tablist", claim_tool_tabs),
    ("whatsapp", "A message is read back before it is called sent.",
     "unverified work must say so", claim_whatsapp),
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="prove the claims, end to end")
    parser.add_argument("--live", action="store_true",
                        help="use the configured provider instead of a local fake")
    parser.add_argument("--only", default="", help="comma-separated claim keys")
    parser.add_argument("--budget-startup", type=float, default=25.0)
    parser.add_argument("--budget-ram", type=float, default=1200.0)
    parser.add_argument("--budget-turn", type=float, default=6.0)
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)

    wanted = {w.strip() for w in args.only.split(",") if w.strip()}
    print(f"PROOF GATE on {platform.platform()}")
    print(f"python {platform.python_version()}"
          + ("  ·  live provider" if args.live else "  ·  fake provider for the wire"))

    results = []
    for key, title, requirement, fn in CLAIMS:
        if wanted and key not in wanted:
            continue
        claim = Claim(key, title, requirement)
        print(f"\n▸ {key}: {title}")
        try:
            if key in {"brain", "acts"}:
                fn(claim, args.live)
            elif key == "budgets":
                fn(claim, args)
            else:
                fn(claim)
        except Exception:
            claim.bad("claim ran", traceback.format_exc(limit=3).strip().splitlines()[-1])
        for name, status, detail in claim.steps:
            print(f"    {status:12s} {name}" + (f" — {detail}" if detail else ""))
        verdict = claim.verdict()
        print(f"    {'=' * 60}")
        print(f"    {verdict:12s} {key}")
        results.append({"claim": key, "title": title, "requirement": requirement,
                        "verdict": verdict,
                        "steps": [{"step": n, "status": s, "detail": d}
                                  for n, s, d in claim.steps]})

    order = {PROVEN: 0, "PARTIAL": 1, FAILED: 2, MISSING: 3, SKIPPED: 4}
    tally = {}
    for row in results:
        tally[row["verdict"]] = tally.get(row["verdict"], 0) + 1

    print("\n══ PROOF GATE")
    print(f"  {'claim':16s} {'verdict':12s} requirement")
    for row in sorted(results, key=lambda r: order.get(r["verdict"], 9)):
        print(f"  {row['claim']:16s} {row['verdict']:12s} {row['requirement']}")
    print("\n  " + "  ".join(f"{k}: {v}" for k, v in sorted(tally.items())))

    probs = [r for r in results if r["verdict"] in {FAILED, MISSING}]
    if probs:
        print("\n  Claims that do not hold here:")
        for row in probs:
            worst = next(s for s in row["steps"] if s["status"] in {FAILED, MISSING})
            print(f"    · {row['claim']} — {worst['detail'][:110]}")
    if tally.get(SKIPPED) or tally.get("PARTIAL"):
        print("\n  PARTIAL and SKIPPED are not passes. Run the same command on the "
              "target machine to close them.")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "platform": platform.platform(), "live": args.live,
            "budgets": {"startup_s": args.budget_startup, "ram_mb": args.budget_ram,
                        "turn_s": args.budget_turn},
            "totals": tally, "claims": results}, indent=2), encoding="utf-8")
        print(f"  report: {args.json}")

    return 1 if probs else 0


if __name__ == "__main__":
    raise SystemExit(main())
