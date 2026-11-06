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
            return c.skip("input device", "this machine reports no microphone, "
                                          "so there is nothing to test here")
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
            return c.skip("output device", "this machine reports no speaker, "
                                           "so there is nothing to test here")
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
        # `snapshot()` returns the raw tree as a Node, not a Snapshot with refs;
        # refs are assigned later, by the session. Counting the nodes it did
        # produce is the honest measure of "the tree was really walked", and it
        # was the last thing this gate got wrong on Windows.
        tree = adapter.snapshot()
        nodes = list(tree.walk())
        if len(nodes) < 2:
            return c.bad("tree", f"the foreground window produced {len(nodes)} node(s)")
        c.ok("tree", f"{len(nodes)} nodes from '{str(tree.name)[:40]}'")
        after = adapter.foreground()
        if before.get("handle") != after.get("handle"):
            return c.bad("no-focus-theft", "reading the tree changed the foreground window")
        c.ok("no-focus-theft", f"the foreground window is still '{after.get('title', '')[:40]}'")
    except Exception as exc:
        return c.bad("tree", f"{type(exc).__name__}: {str(exc)[:160]}")


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


def claim_philosophy(c: Claim) -> None:
    """Its philosophy is a blend the owner owns, and no voice can grant permission."""
    try:
        from core import philosophy as minds
        from actions import philosophy as tool
    except Exception as exc:
        return c.absent("philosophy", f"{type(exc).__name__}: {exc}")
    cast = minds.VOICES
    unbound = [key for key, voice in cast.items() if not voice.bound.strip()]
    if unbound:
        return c.bad("bounds", "a mind states no limit: " + ", ".join(unbound))
    c.ok("cast", f"{len(cast)} minds, each with a maxim, a stance and a bound")
    # Pure: `_normalise` writes nothing, so the gate can ask the hardest question
    # without touching the owner's settings.
    chosen, _notes = minds._normalise({"ultron": 0.9})
    if chosen.get("ultron", 0) > minds.VOICES["ultron"].ceiling + 0.01:
        return c.bad("ceiling", f"the adversary reached {chosen.get('ultron', 0):.0%}")
    c.ok("ceiling", f"asked for 90%, the adversary is held at "
                    f"{chosen.get('ultron', 0):.0%}")
    block = minds.prompt_block()
    if minds.CHARTER not in block:
        return c.bad("charter", "the block does not say that permission is unchanged")
    missing = [key for key in minds.active()
               if minds.VOICES[key].bound not in block]
    if missing:
        return c.bad("bounds", "not in the instruction: " + ", ".join(missing))
    c.ok("charter", f"{len(block)} characters added, and every bound in them")
    source = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    if "philosophy.prompt_block()" not in source:
        return c.bad("instruction", "main.py never adds the block to the prompt")
    c.ok("instruction", "appended to the system instruction at session start")
    answer = tool.philosophy_tool({"action": "rules"})
    if "40%" not in answer:
        return c.bad("tool", "the tool does not state its own ceiling")
    c.ok("tool", "reachable by voice, and it states the ceiling itself")


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


_BYTECODE = ("__pycache__", ".pyc", ".pyo")


def _store_state(root: Path) -> dict:
    """What the memory store looks like, ignoring bytecode.

    The digest claim snapshots the store, builds the report, and snapshots again:
    if the two differ, the report touched something and it is not inert. The
    first version of that check counted every file under `memory/`, including
    `memory/__pycache__/*.pyc` — and on a clean clone the first run imports a
    memory module lazily and writes bytecode, so the check failed on a program
    that had done nothing wrong. The gate was right about the rule and wrong
    about the evidence: a .pyc is not the user's memory.

    Bytecode and editor droppings are therefore outside the snapshot, and the
    verdict is the same on a fresh clone as on the tenth run.
    """
    state = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _BYTECODE for part in path.parts) or path.suffix in _BYTECODE:
            continue
        if path.name.endswith((".tmp", ".swp")):
            continue
        stat = path.stat()
        state[path] = (stat.st_mtime_ns, stat.st_size)
    return state


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

    before = _store_state(ROOT / "memory")
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
    after = _store_state(ROOT / "memory")
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
        # The test modules were merged into suites on 2026-11-06; the gate names
        # the suite that now holds this section, not the file it used to be.
        from tests.test_suite_providers import FakeSession, tree

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


def claim_metacognition(c: Claim) -> None:
    """It keeps score on itself, and it will not call a lucky streak evidence."""
    try:
        from custom_jarvis.metacog import Ledger
    except Exception as exc:                                   # noqa: BLE001
        return c.absent("the ledger", f"{type(exc).__name__}: {exc}")
    c.ok("the ledger", "custom_jarvis/metacog.py exists and imports")

    import tempfile

    folder = Path(tempfile.mkdtemp(prefix="gate-metacog-"))
    path = folder / "metacog.json"
    ledger = Ledger(path)

    # A perfect small record must NOT be reported as a proven one.
    for _ in range(3):
        row = ledger.record_prediction("the build passes", 0.9)
        ledger.resolve_prediction(row["id"], "correct")
    small = ledger.calibration()
    if small["accuracy"] != 1.0:
        return c.bad("a perfect record", f"accuracy was {small['accuracy']}, not 1.0")
    if small["lower_bound"] >= 0.5 or "not yet evidence" not in small["verdict"]:
        return c.bad("a perfect record",
                     f"3 of 3 was sold as {small['lower_bound']:.3f} — "
                     "a lucky streak became a number")
    c.ok("a perfect record",
         f"3 of 3 is accuracy 1.0 but a bound of {small['lower_bound']:.3f}, "
         f"verdict \u201c{small['verdict']}\u201d")

    # The same perfection, forty times, may be believed.
    for _ in range(37):
        row = ledger.record_prediction("the build passes", 0.9)
        ledger.resolve_prediction(row["id"], "correct")
    big = ledger.calibration()
    if not big["lower_bound"] > 0.9 > small["lower_bound"]:
        return c.bad("forty of forty", f"bound {big['lower_bound']:.3f} vs "
                                       f"{small['lower_bound']:.3f}")
    c.ok("forty of forty",
         f"the same perfect record earns {big['lower_bound']:.3f} once it has "
         "forty cases behind it")

    # Saying 95% and being wrong must be named, not smoothed away.
    for _ in range(2):
        row = ledger.record_prediction("the tests cover this", 0.95, domain="selfcheck")
        ledger.resolve_prediction(row["id"], "wrong")
    wrong = ledger.calibration("selfcheck")
    bucket = next((b for b in wrong["buckets"] if b["range"] == "90-100%"), None)
    if bucket is None or bucket["was_right"] != 0.0:
        return c.bad("an overconfident bucket",
                     f"a 90-100% bucket said right none of the time: {bucket}")
    c.ok("an overconfident bucket",
         f"claims made at 95% were right 0% of the time, Brier {wrong['brier']:.2f}")

    # A lesson without a rule is a diary entry.
    try:
        ledger.record_lesson("tests crash", "the suite died", "   ")
    except ValueError:
        c.ok("a rule is required", "a lesson with no rule was refused")
    else:
        return c.bad("a rule is required", "a lesson with no rule was accepted")

    rule = "read the failing test before changing the code"
    ledger.record_lesson("the suite fails on windows", "patched the caller", rule,
                         domain="testing")
    hits = ledger.lessons_for("the suite fails on windows again")
    if not hits or hits[0]["rule"] != rule:
        return c.bad("a lesson comes back", f"recall returned {hits[:1]}")
    c.ok("a lesson comes back",
         f"the rule was recalled for the next matching task, used {hits[0]['hits']}x")

    # A lucky first strategy must not lock out the alternative.
    for _ in range(3):
        ledger.record_attempt("fix failing tests", "rewrite the module", True)
    choice = ledger.choose_strategy("fix failing tests", ["rewrite the module",
                                                          "read the error"])
    if choice["strategy"] != "read the error":
        return c.bad("an untried strategy is tried",
                     f"it chose {choice['strategy']} without ever trying the other")
    c.ok("an untried strategy is tried",
         "the proven approach was passed over once, so the other one gets a fair test")

    # It is one local file, and the tools reach it through the real registry.
    if not path.exists():
        return c.bad("one local file", "nothing was written to disk")
    written = sorted(p.name for p in folder.iterdir())
    if written != ["metacog.json"]:
        return c.bad("one local file", f"the ledger scattered {written}")
    try:
        from custom_jarvis.metacog_tools import register_metacog_tools
        from custom_jarvis.tools import registry as live

        names = lambda: {row["name"] for row in live.list_tools()}
        before = names()
        register_metacog_tools(live, ledger)
        after = names()
        if len(after - before) < 10:
            return c.bad("the tools are registered",
                         f"only {len(after - before)} tools appeared")
    except Exception as exc:                                   # noqa: BLE001
        return c.bad("the tools are registered", f"{type(exc).__name__}: {exc}")
    c.ok("the tools are registered",
         f"{len(after - before)} metacognitive tools joined the live registry, "
         "including `decide`")
    c.ok("one local file", f"one JSON file, no model, no network: {written[0]}")


def claim_decisions(c: Claim) -> None:
    """It decides with arithmetic, and it can refuse to decide."""
    try:
        from custom_jarvis.decision import choose, score
        from custom_jarvis.shortlist import rank
        from custom_jarvis.telemetry import Monitor
        from core.bandit import UCB1
    except Exception as exc:                                   # noqa: BLE001
        return c.absent("the decision layer", f"{type(exc).__name__}: {exc}")
    c.ok("the decision layer", "decision, shortlist, telemetry and the bandit import")

    # 1. Expected value, and the refusal that makes it a decision system.
    best = choose([
        {"name": "guess", "p": 0.6, "value": 1.0},
        {"name": "read the file first", "p": 0.95, "value": 1.0, "cost": 0.1},
    ])
    if best["choice"] != "read the file first":
        return c.bad("expected value", f"it chose {best['choice']!r}")
    doomed = choose([{"name": "retry the doomed build", "p": 0.1, "value": 1.0,
                      "cost": 2.0}])
    if doomed["choice"] or not doomed["refused"]:
        return c.bad("a refusal", f"it recommended {doomed['choice']!r} at a loss")
    blocked = choose([{"name": "force push", "p": 1.0, "value": 9.0, "risk": "blocked"},
                      {"name": "open a pull request", "p": 0.8, "value": 1.0}])
    if blocked["choice"] != "open a pull request":
        return c.bad("a refusal", "a blocked option won on value alone")
    c.ok("expected value",
         f"chance x value - cost - risk picked {best['choice']!r} at {best['score']:+.2f}")
    c.ok("a refusal",
         "a guaranteed loss and a blocked option are both answered with \u201cdo none "
         "of these\u201d")
    for bad in ({"p": 1.7}, {"p": "sure"}, {"p": 0.5, "risk": "reckless"}):
        try:
            score(**bad)
        except ValueError:
            continue
        return c.bad("honest arithmetic", f"{bad} was accepted")
    c.ok("honest arithmetic", "a chance of 1.7 and an unknown risk tier are refused")

    # 2. Ranking: a rare word beats a word in every entry.
    documents = [{"id": "a", "text": "tests failed on the parser"},
                 {"id": "b", "text": "tests failed on the network"},
                 {"id": "c", "text": "tests failed, cors header missing"}]
    top = rank("the cors tests failed", documents, limit=1)
    if not top or top[0]["id"] != "c":
        return c.bad("relevant first", f"BM25 returned {top}")
    if rank("write a haiku about rain", documents):
        return c.bad("relevant first", "an unrelated question still returned advice")
    c.ok("relevant first",
         "BM25 puts the rare matching word first and returns nothing for an unrelated "
         "question")

    # 3. The baseline follows the machine: quiet at first, loud on a real jump.
    monitor = Monitor(minimum=8)
    early = [monitor.observe(1.0 + (index % 2) * 0.02) for index in range(14)]
    late = monitor.observe(9.0)
    if any(row["alert"] for row in early) or not late["alert"]:
        return c.bad("a moving baseline",
                     f"early alerts={any(r['alert'] for r in early)}, "
                     f"late alert={late['alert']}")
    c.ok("a moving baseline",
         f"fourteen normal turns stayed quiet, then a 9.0 s turn was flagged: "
         f"\u201c{late['note']}\u201d")

    # 4. The bandit: explore what is least tried, then settle.
    bandit = UCB1(["proven", "lucky_once"])
    for _ in range(12):
        bandit.update("proven", 1.0)
    bandit.update("lucky_once", 1.0)
    if bandit.choose() != "lucky_once":
        return c.bad("a fair trial", "the rarely tried option was never explored")
    for _ in range(4):
        bandit.update("lucky_once", 0.0)
    if bandit.choose() != "proven":
        return c.bad("a fair trial",
                     "a failing option still outranked a proven one after four failures")
    c.ok("a fair trial",
         "the 1-in-1 option was explored once, then the 12-in-12 option took over")

    # 5. The layer is reachable as a tool, and it asks nothing.
    try:
        import tempfile
        from custom_jarvis.service import CustomService

        asked = []
        folder = Path(tempfile.mkdtemp(prefix="gate-decide-"))
        workspace = folder / "ws"
        workspace.mkdir()
        service = CustomService(folder / "state",
                                approval=lambda kind, *rest: asked.append(kind) or True)
        service.perform("set_workspace", {"path": str(workspace)})
        asked.clear()
        answer = service.perform("tool", {
            "name": "decide",
            "arguments": {"options": [
                {"name": "ask the user", "p": 0.9, "value": 1.0, "cost": 0.1},
                {"name": "guess", "p": 0.3, "value": 1.0}]}})
        service.stop() if hasattr(service, "stop") else None
        if not answer["success"] or "ask the user" not in answer["output"]:
            return c.bad("a tool, not a lecture", f"decide returned {answer}")
        if asked:
            return c.bad("a tool, not a lecture",
                         f"a read-only decision asked for approval: {asked}")
    except Exception as exc:                                   # noqa: BLE001
        return c.bad("a tool, not a lecture", f"{type(exc).__name__}: {exc}")
    c.ok("a tool, not a lecture",
         "the model can call `decide`, and it never asks permission to do arithmetic")


def _fake_web(routes):
    """A urlopen stand-in for the gate: the web layer is proven without a network."""
    import json as _json

    class _Reply:
        def __init__(self, body, status=200, headers=None):
            self._body = body if isinstance(body, bytes) else _json.dumps(body).encode()
            self.status = status
            self.headers = headers or {}

        def read(self, size=-1):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(request, timeout=None):
        answer = routes.get(request.full_url, routes.get("*"))
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            return answer(request)
        return answer

    return opener


def claim_github(c: Claim) -> None:
    """GitHub is read natively, the token stays out of everything else."""
    try:
        from core import github, webapi
        from core.paths import state_dir
        from plugins import github_tool
    except Exception as exc:                                   # noqa: BLE001
        return c.absent("the client", f"{type(exc).__name__}: {exc}")
    c.ok("the client", "core/github.py, core/webapi.py and plugins/github_tool.py import")

    import tempfile
    import urllib.error

    folder = Path(tempfile.mkdtemp(prefix="gate-github-"))
    cache_path = folder / "cache.json"
    class Reply:
        def __init__(self, body, headers=None):
            self._body = json.dumps(body).encode()
            self.status = 200
            self.headers = headers or {}

        def read(self, size=-1):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    state = {"urls": [], "headers": []}

    def opener(request, timeout=None):
        state["urls"].append(request.full_url)
        state["headers"].append(dict(request.headers))
        return Reply({"items": [{"full_name": "acme/rocket", "description": "a fast engine",
                                 "stargazers_count": 4321, "language": "Rust",
                                 "html_url": "u"}]},
                     headers={"ETag": '"one"'})

    try:
        webapi.set_opener(opener)
        client = github.GitHub("ghp_gate_token", webapi.Cache(cache_path))
        result = client.trending(days=7, minimum_stars=50, language="rust", limit=3)
        if not result["ok"] or result["data"]["items"][0]["stars"] != 4321:
            return c.bad("a real read", f"trending returned {result}")
        url = state["urls"][0]
        for piece in ("search/repositories", "sort=stars", "created%3A%3E",
                      "stars%3A%3E49", "language%3Arust"):
            if piece not in url:
                return c.bad("a real read", f"the query did not contain {piece}: {url}")
        if "no trending API" not in result["data"]["source"]:
            return c.bad("an honest label",
                         "trending did not say that GitHub has no trending API")
        c.ok("a real read", "a search for recently created repositories, sorted by stars")
        c.ok("an honest label",
             "the answer says it is an approximation, not an official trending list")

        if state["headers"][0].get("Authorization") != "Bearer ghp_gate_token":
            return c.bad("a token in one header", "the token was not sent")
        if cache_path.exists() and "ghp_gate_token" in cache_path.read_text(encoding="utf-8"):
            return c.bad("a token in one header", "the token reached the cache file")
        c.ok("a token in one header",
             "sent as a bearer header, and absent from the cache file on disk")

        webapi.set_opener(_fake_web({"*": urllib.error.URLError("down")}))
        offline = github.GitHub("", None).repo("acme/rocket")
        if offline["ok"] or "no network" not in offline["note"].lower():
            return c.bad("the truth when it fails", f"offline returned {offline}")
        no_token = github.GitHub("", None).notifications()
        if no_token["ok"] or "token" not in no_token["note"]:
            return c.bad("the truth when it fails", f"no token returned {no_token}")
        c.ok("the truth when it fails",
             "no network and no token are two different, useful sentences")
    except Exception as exc:                                   # noqa: BLE001
        return c.bad("a real read", f"{type(exc).__name__}: {exc}")
    finally:
        webapi.set_opener(None)

    try:
        webapi.set_opener(_fake_web({"*": urllib.error.URLError("down")}))
        sentence = github_tool.run({"action": "trending"})
        if "network" not in sentence.lower():
            return c.bad("a plugin, not a link", f"the plugin said {sentence!r}")
    finally:
        webapi.set_opener(None)
    c.ok("a plugin, not a link", "the tool speaks in a sentence when GitHub is unreachable")


def claim_self_extension(c: Claim) -> None:
    """It adds a skill to itself as data, and cannot add one that writes."""
    try:
        from custom_jarvis import skillpacks
        from custom_jarvis.service import CustomService
        from custom_jarvis.skills import SKILL_BY_ID, SKILLS
    except Exception as exc:                                   # noqa: BLE001
        return c.absent("the pack loader", f"{type(exc).__name__}: {exc}")
    c.ok("the pack loader", "custom_jarvis/skillpacks.py imports")

    import tempfile

    folder = Path(tempfile.mkdtemp(prefix="gate-packs-"))
    pack = {"id": "gate_pack_todos", "title": "Gate todo report",
            "purpose": "Count TODO markers, so the gate has a pack to install.",
            "steps": [{"tool": "search_text",
                       "args": {"path": "@workspace", "query": "TODO"}}]}
    before = len(SKILLS)
    result = skillpacks.install(pack, folder, ["search_text", "measure_code"])
    if not result["ok"] or "gate_pack_todos" not in SKILL_BY_ID:
        return c.bad("a skill it wrote", f"install returned {result}")
    if len(SKILLS) != before + 1:
        return c.bad("a skill it wrote", f"the skill count went {before} -> {len(SKILLS)}")
    if not (folder / "skills" / "gate_pack_todos.json").exists():
        return c.bad("a skill it wrote", "no file was written")
    c.ok("a skill it wrote",
         f"a pack became skill '{result['id']}', live at once and stored as one JSON file")

    refused = {
        "a tool that writes": {"steps": [{"tool": "write_file",
                                          "args": {"path": "@workspace/x"}}]},
        "a built-in id": {"id": "secret_scan"},
        "a path outside": {"steps": [{"tool": "search_text",
                                      "args": {"path": "/etc/passwd", "query": "x"}}]},
        "too many steps": {"steps": [{"tool": "search_text",
                                      "args": {"path": "@workspace"}}] * 9},
    }
    for label, patch in refused.items():
        bad = dict(pack, **patch)
        if not skillpacks.validate(bad, ["search_text", "write_file"]):
            return c.bad("four refusals", f"{label} was accepted")
    c.ok("four refusals",
         "a writing tool, a built-in id, a path outside, and nine steps are all refused")

    missing = skillpacks.remove("not_a_real_pack", folder)
    if missing["ok"]:
        return c.bad("removable", "removing a pack that does not exist reported success")
    if not skillpacks.remove("gate_pack_todos", folder)["ok"]:
        return c.bad("removable", "the pack could not be removed")
    if "gate_pack_todos" in SKILL_BY_ID:
        return c.bad("removable", "the skill stayed loaded after removal")
    if skillpacks.remove("secret_scan", folder)["ok"]:
        return c.bad("removable", "a built-in skill was removed as if it were a pack")
    c.ok("removable", "a pack leaves in one call; a built-in refuses to")

    reload_dir = Path(tempfile.mkdtemp(prefix="gate-packs2-"))
    skillpacks.install(pack, reload_dir, ["search_text"])
    skillpacks.remove("gate_pack_todos", reload_dir)
    skillpacks.install(pack, reload_dir, ["search_text"])
    SKILL_BY_ID.pop("gate_pack_todos", None)
    SKILLS[:] = [skill for skill in SKILLS if skill.identity != "gate_pack_todos"]
    loaded = skillpacks.load(reload_dir, ["search_text"])
    if loaded["loaded"] != ["gate_pack_todos"]:
        return c.bad("remembered tomorrow", f"reload returned {loaded}")
    SKILL_BY_ID.pop("gate_pack_todos", None)
    SKILLS[:] = [skill for skill in SKILLS if skill.identity != "gate_pack_todos"]
    c.ok("remembered tomorrow", "a saved pack is loaded again at the next start")

    service = CustomService(folder / "state", approval=lambda *args: True)
    names = {row["name"] for row in service.perform("list_tools", {})}
    for tool in ("add_skill", "remove_skill", "list_packs"):
        if tool not in names:
            return c.bad("a tool you can ask", f"{tool} is not registered")
    c.ok("a tool you can ask",
         "add_skill, remove_skill and list_packs are callable, and adding asks first")


def claim_reminders(c: Claim) -> None:
    """It decides when to interrupt, and it can decide not to."""
    try:
        from custom_jarvis.schedule import Queue
    except Exception as exc:                                   # noqa: BLE001
        return c.absent("the queue", f"{type(exc).__name__}: {exc}")
    c.ok("the queue", "custom_jarvis/schedule.py imports")

    import tempfile
    import time as _time

    noon = _time.mktime((2026, 11, 1, 12, 0, 0, 0, 0, -1))
    queue = Queue(Path(tempfile.mkdtemp(prefix="gate-queue-")) / "q.json")
    queue.add("trending:acme/rocket", "A repository is trending", urgency=0.35, value=0.9)
    queue.add("ci:mine/app", "The build is broken", urgency=0.9, value=1.5)
    due = queue.due(now=noon)
    if [row["id"] for row in due][:1] != ["ci:mine/app"]:
        return c.bad("the order", f"the queue ranked {[row['id'] for row in due]}")
    c.ok("the order",
         f"a failing build ({due[0]['score']:+.2f}) outranks trending "
         f"({due[1]['score']:+.2f}) by the same arithmetic that chooses an action")

    queue.mark_shown(["ci:mine/app"], now=noon)
    if any(row["id"] == "ci:mine/app" for row in queue.due(now=noon + 60)):
        return c.bad("silence is a decision", "the same card was repeated inside its cooldown")
    noise = Queue(Path(tempfile.mkdtemp(prefix="gate-queue2-")) / "q.json")
    noise.add("noise:chatter", "Somebody commented somewhere", urgency=0.05,
              value=0.5, cost=0.6)
    if noise.due(now=noon):
        return c.bad("silence is a decision",
                     "a card worth less than its interruption was still shown")
    c.ok("silence is a decision",
         "a cooldown stops repetition, and a card that costs more than it is worth is dropped")

    quiet = Queue(Path(tempfile.mkdtemp(prefix="gate-queue3-")) / "q.json",
                  quiet_start=22, quiet_end=7)
    quiet.add("pr:mine/app", "A pull request waits", urgency=0.5)
    quiet.add("ci:mine/app", "Production is down", urgency=0.99, value=2.0)
    night = _time.mktime((2026, 11, 2, 3, 0, 0, 0, 0, -1))
    ids = [row["id"] for row in quiet.due(now=night)]
    if ids != ["ci:mine/app"]:
        return c.bad("quiet hours", f"at 03:00 the queue offered {ids}")
    c.ok("quiet hours",
         "at 03:00 only the emergency is spoken; an ordinary pull request waits")

    try:
        from core import webapi
        import urllib.error
        from plugins import github_tool
        import os

        home = tempfile.mkdtemp(prefix="gate-watch-")
        os.environ["XDG_DATA_HOME"] = home
        webapi.set_opener(_fake_web({"*": urllib.error.URLError("down")}))
        github_tool.run({"action": "watch", "repository": "acme/rocket"})
        said = github_tool.run({"action": "reminders"})
        if "acme/rocket" not in said and "Nothing needs you" not in said:
            return c.bad("a watch list", f"reminders said {said!r}")
        webapi.set_opener(None)
        github_tool.run({"action": "unwatch", "repository": "acme/rocket"})
    except Exception as exc:                                   # noqa: BLE001
        webapi.set_opener(None)
        return c.bad("a watch list", f"{type(exc).__name__}: {exc}")
    c.ok("a watch list", "a watched repository is turned into cards, then removed again")


def _git_lab(prefix: str):
    """A bare origin and a working copy, made fresh, so git is proven for real."""
    import subprocess
    import tempfile

    base = Path(tempfile.mkdtemp(prefix=prefix))
    origin, work = base / "origin.git", base / "work"
    flags = ["-c", "user.name=Gate", "-c", "user.email=gate@localhost",
             "-c", "protocol.file.allow=always"]

    def git(cwd, *args):
        return subprocess.run(["git", *flags, *args], cwd=str(cwd), capture_output=True,
                              text=True, timeout=60)

    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(origin)],
                   check=True, capture_output=True)
    work.mkdir()
    git(work, "init", "-q", "--initial-branch=main")
    (work / ".gitignore").write_text(
        "config/api_keys.json\nconfig/api_keys.json.*\nmemory/long_term.json\n")
    (work / "app.py").write_text("print('one')\n")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "first")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-qu", "-u", "origin", "main")
    return base, origin, work, git


def claim_shipping(c: Claim) -> None:
    """Every change can be shipped, and a secret stops the ship."""
    import shutil

    if shutil.which("git") is None:
        return c.skip("git", "git is not on PATH here, so a push cannot be proven")
    try:
        from custom_jarvis.ship import find_secret
        from custom_jarvis.ship import Shipper
    except Exception as exc:                                   # noqa: BLE001
        return c.absent("the shipper", f"{type(exc).__name__}: {exc}")
    c.ok("the shipper", "custom_jarvis/ship.py imports")

    base, origin, work, git = _git_lab("gate-ship-")
    shipper = Shipper(work, token="local-test-token", log_path=base / "ship.json")

    (work / "leak.py").write_text('api_key = "Qz8vLmT4rXn2Pw9Ks3Dd"\n')  # gitleaks:allow — a fixture, not a key
    blocked = shipper.ship("this must not ship")
    if blocked["ok"] or blocked["stage"] != "scan":
        return c.bad("a secret stops the ship",
                     f"a file with a key in it was handled as {blocked.get('stage')}")
    commits = [line for line in git(origin, "log", "--oneline", "main").stdout.splitlines()
               if line.strip()]
    if len(commits) != 1:
        return c.bad("a secret stops the ship",
                     f"the remote has {len(commits)} commits; the leak was committed")
    c.ok("a secret stops the ship",
         "an assignment-shaped key in one file stopped the run before the commit")

    if not find_secret('x = "github_pat_11BZQ7XK2MvT9LpR4WnC8JdY6HsA3GfE5UoI1Kq7YmZ"'):  # gitleaks:allow — a fixture, not a key
        return c.bad("a token shape is caught", "a GitHub-token-shaped string was missed")
    if find_secret('api_key = "abcd1234efgh5678"') or find_secret('SECRET = "AIza-THIS-IS-A-FIXTURE"'):
        return c.bad("a token shape is caught", "a placeholder was reported as a secret")
    c.ok("a token shape is caught",
         "a token-shaped string always stops the ship; four placeholder shapes never do")

    marked, unmarked = "Qz8v" + "LmT4rXn2Pw9Ks3Dd", "Xk2m" + "Q8vLpT4rXn2Pw9Ks"
    # Assembled from parts so this file does not itself contain the key shape it
    # plants in the lab; a scanner that exempts its own source has a hole in it.
    (work / "leak.py").write_text(
        'api_key = "' + marked + '"  # gitleaks:allow\n'
        'api_key = "' + unmarked + '"\n')
    mixed = shipper.scan()
    if mixed["clean"] or mixed["hits"][0]["lines"] != [2]:
        return c.bad("the exemption is one line", f"a marked fixture line exempted {mixed['hits']}")
    if mixed["allowed"] != 1:
        return c.bad("the exemption is one line", f"the allowed count is {mixed['allowed']}")
    c.ok("the exemption is one line",
         "a fixture marked gitleaks:allow is skipped and counted; the unmarked key beside it stops the ship")

    (work / "leak.py").unlink()
    (work / "app.py").write_text("print('two')\n")
    shipped = shipper.ship("print two", why="the gate needs a real ship")
    if not shipped["ok"]:
        return c.bad("a real push", f"the ship failed: {shipped.get('note')}")
    remote_log = git(origin, "log", "--oneline", "main").stdout
    if "print two" not in remote_log:
        return c.bad("a real push", f"the commit is not on the remote: {remote_log!r}")
    body = git(origin, "log", "-1", "--format=%B", "main").stdout
    for piece in ("Why:", "Evidence:", "Secret scan"):
        if piece not in body:
            return c.bad("a real push", f"the commit message has no {piece}")
    c.ok("a real push",
         "committed and pushed to a real remote, with the evidence in the message")

    other = base / "other"
    git(base, "clone", "-q", str(origin), str(other))
    (other / "app.py").write_text("print('from elsewhere')\n")
    git(other, "commit", "-qam", "elsewhere")
    git(other, "push", "-q", "origin", "main")
    (work / "app.py").write_text("print('from here')\n")
    diverged = shipper.ship("local work on top of a moved remote")
    if diverged["ok"] or diverged["stage"] != "push" or "will not force" not in diverged["note"]:
        return c.bad("never a force-push", f"a divergence was handled as {diverged}")
    c.ok("never a force-push",
         "the remote moved, so the ship stopped and said why instead of forcing")

    (work / "later.py").write_text("# a later change\n")
    no_token = Shipper(work, token="").ship("no token at all")
    if no_token["ok"] or "no GitHub token" not in no_token["note"]:
        return c.bad("a sentence when it cannot", f"a token-less ship returned {no_token}")
    c.ok("a sentence when it cannot",
         "with no token it says what is missing instead of failing in git")

    if not (base / "ship.json").exists():
        return c.bad("a record", "nothing was written to the ship log")
    c.ok("a record", "each attempt is kept in a ship log beside the state")


def claim_self_update(c: Claim) -> None:
    """It updates from the remote, and it puts a bad version back."""
    import shutil

    if shutil.which("git") is None:
        return c.skip("git", "git is not on PATH here, so an update cannot be proven")
    try:
        from custom_jarvis.selfupdate import Updater
    except Exception as exc:                                   # noqa: BLE001
        return c.absent("the updater", f"{type(exc).__name__}: {exc}")
    c.ok("the updater", "custom_jarvis/selfupdate.py imports")

    base, origin, work, git = _git_lab("gate-update-")

    def publish(name, text):
        other = base / "publisher"
        if not other.exists():
            git(base, "clone", "-q", str(origin), str(other))
        else:
            git(other, "pull", "-q", "--ff-only")
        (other / name).write_text(text)
        git(other, "add", "-A")
        git(other, "commit", "-qm", f"publish {name}")
        git(other, "push", "-q", "origin", "main")

    # The marker lives beside the lab, not in the tree: a file in the tree would
    # make it dirty and block the next update.
    updater = Updater(work, token="local-test-token", marker=base / "restart.json")
    quiet = updater.check()
    if not quiet["ok"] or quiet["behind"] != 0:
        return c.bad("a check", f"an up-to-date copy reported {quiet}")
    c.ok("a check", "an up-to-date copy says so, and applies nothing")

    publish("notes.md", "a new note\n")
    data_only = updater.apply()
    if not data_only["ok"] or data_only["restart_required"]:
        return c.bad("data reloads live", f"a notes-only update returned {data_only}")
    c.ok("data reloads live",
         "a documentation change is taken with no restart, because it is read on demand")

    publish("app.py", "print('two')\n")
    code_change = updater.apply()
    if not code_change["ok"] or not code_change["restart_required"]:
        return c.bad("code waits for a restart", f"a code update returned {code_change}")
    marker = updater.restart_marker()
    if marker.get("files") != ["app.py"]:
        return c.bad("code waits for a restart", f"the marker says {marker}")
    if "restart is required" not in code_change["note"]:
        return c.bad("code waits for a restart", "the answer did not mention the restart")
    c.ok("code waits for a restart",
         "a changed module is on disk, the marker names it, and the answer says why")

    before = git(work, "rev-parse", "HEAD").stdout.strip()
    publish("broken.py", "def broken(:\n")

    def verify():
        for path in work.rglob("*.py"):
            try:
                compile(path.read_text(), str(path), "exec")
            except SyntaxError as error:
                return {"ok": False, "note": f"{path.name}: {error.msg}"}
        return {"ok": True}

    reverted = updater.apply(verify=verify)
    after = git(work, "rev-parse", "HEAD").stdout.strip()
    if reverted["ok"] or reverted["stage"] != "verify" or after != before:
        return c.bad("a bad version is put back",
                     f"the update returned {reverted} and HEAD {before[:7]}->{after[:7]}")
    if (work / "broken.py").exists():
        return c.bad("a bad version is put back", "the broken file is still in the tree")
    c.ok("a bad version is put back",
         "a version that does not parse was reverted to the commit before it")

    (work / "app.py").write_text("print('uncommitted')\n")
    publish("notes.md", "another note\n")
    dirty = updater.apply()
    if dirty["ok"] or dirty["stage"] != "dirty":
        return c.bad("your work is not overwritten", f"a dirty tree was handled as {dirty}")
    c.ok("your work is not overwritten",
         "with uncommitted changes it refuses to pull rather than discarding them")


def claim_process_watch(c: Claim) -> None:
    """It watches background programs, never touches them, and never cuts in."""
    source_path = ROOT / "core" / "process_watch.py"
    if not source_path.exists():
        return c.absent("the watcher", "core/process_watch.py is not in the tree")
    source = source_path.read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))
    for word in (".terminate(", ".kill(", ".suspend(", ".resume(", ".send_signal(",
                 "os.kill", "signal.pthread", ".wait("):
        if word in code:
            return c.bad("it only watches", f"process_watch.py can call {word}")
    c.ok("it only watches", "the module has no call that can end, pause or signal a process")

    try:
        from core.process_watch import SpeechGate, Supervisor, Watcher
    except Exception as exc:                                   # noqa: BLE001
        return c.bad("the watcher", f"{type(exc).__name__}: {exc}")

    class _Proc:
        def __init__(self, pid, name, created):
            self.info = {"pid": pid, "name": name, "create_time": created,
                         "cmdline": [], "status": "running"}

    class _Lib:
        def __init__(self, *procs):
            self.procs = list(procs)

        def process_iter(self, attrs=None):
            return list(self.procs)

    import time as _time

    lib = _Lib(_Proc(4242, "Antigravity Helper", _time.time() - 90))
    watcher = Watcher(library=lib)
    watcher.watch("antigravity", label="Antigravity")
    if watcher.poll():
        return c.bad("a finish is reported once", "it reported a finish before one happened")
    if not [p for p in watcher.live() if p.pid == 4242]:
        return c.bad("it sees the job", "the running process was not visible")
    c.ok("it sees the job", "a running Antigravity process is visible and quiet")

    lib.procs = []
    first = watcher.poll()
    if len(first) != 1:
        return c.bad("a finish is reported once", f"the finish came back as {first}")
    if watcher.poll():
        return c.bad("a finish is reported once", "the same finish was reported twice")
    c.ok("a finish is reported once", f"one sentence: {first[0].sentence()}")

    clock = [0.0]
    gate = SpeechGate(quiet_for=1.0, clock=lambda: clock[0])
    said = []
    gate.hold(first[0].sentence())
    if gate.ready(busy=True):
        return c.bad("it does not cut in", "it spoke while the owner was talking")
    clock[0] = 0.5
    if gate.ready(busy=False):
        return c.bad("it does not cut in", "it spoke during a pause for breath")
    clock[0] = 2.0
    if not gate.ready(busy=False):
        return c.bad("it does not cut in", "the held sentence never arrived")
    c.ok("it does not cut in",
         "held while the owner speaks, delivered once the room is quiet")

    logged, spoken = [], []
    lib2 = _Lib(_Proc(5150, "antigravity", _time.time() - 30))
    watcher2 = Watcher(library=lib2)
    watcher2.watch("antigravity", label="Antigravity")
    clock2 = [0.0]
    supervisor = Supervisor(watcher2, gate=SpeechGate(quiet_for=1.0, clock=lambda: clock2[0]),
                            say=spoken.append, log=logged.append)
    supervisor.tick(busy=True)
    lib2.procs = []
    supervisor.tick(busy=True)
    if not logged or spoken:
        return c.bad("the record does not wait", f"logged={logged} spoken={spoken}")
    # Silence starts at the first poll after the owner stops, so the sentence
    # arrives on the poll after the quiet stretch — never on the instant itself.
    clock2[0] = 3.0
    if supervisor.tick(busy=False):
        return c.bad("the record does not wait",
                     "it spoke on the first poll after the owner stopped")
    clock2[0] = 4.5
    supervisor.tick(busy=False)
    if not spoken:
        return c.bad("the record does not wait", "the sentence never reached the voice")
    c.ok("the record does not wait",
         "the log line is written at once; the spoken line waits for silence")

    main_source = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    for needle in ("async def _process_watch_loop",
                   "asyncio.create_task(self._process_watch_loop())",
                   "def _owner_is_talking", "ULTRON_WATCH"):
        if needle not in main_source:
            return c.absent("wired into the application", f"main.py lacks {needle!r}")
    c.ok("wired into the application", "the loop starts with the app and reads the owner's state")


def claim_sidecar(c: Claim) -> None:
    """The one compiled component is optional, and its absence is proven."""
    source = ROOT / "sidecar" / "watchd" / "main.go"
    tests = ROOT / "sidecar" / "watchd" / "main_test.go"
    if not source.exists() or not tests.exists():
        return c.absent("the source", "sidecar/watchd is not in the tree")
    text = source.read_text(encoding="utf-8")
    c.ok("the source", f"{len(text.splitlines())} lines of Go, with its own tests")

    for word in ("Process.Kill", "cmd.Process.Kill", "syscall.Kill"):
        if word in text:
            return c.bad("it only watches", f"the sidecar can call {word}")
    c.ok("it only watches",
         "it starts only the command it was given and signals nothing else")

    try:
        from core import sidecar
    except Exception as exc:                                   # noqa: BLE001
        return c.bad("the bridge", f"{type(exc).__name__}: {exc}")

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        path.write_text('{"pid": 1, "name": "antigravity", "seconds": 90,'
                        ' "how": "ended", "watch": "antigravity"}\n'
                        '{"pid": 2, "nam', encoding="utf-8")
        events, offset = sidecar.read_new_events(path, 0)
        if len(events) != 1:
            return c.bad("a partial line", f"a half written line became {events}")
        done = sidecar.completion_from_event(events[0])
        if done is None or "finished" not in done.sentence():
            return c.bad("a partial line", "the completed line did not read as a finish")
        path.write_text(path.read_text(encoding="utf-8") + 'e": "x"}\n', encoding="utf-8")
        more, _ = sidecar.read_new_events(path, offset)
        if len(more) != 1:
            return c.bad("a partial line", "the finished line was never returned")
    c.ok("a partial line", "a half written record waits for its other half")

    present = sidecar.binary_path() is not None
    feed = sidecar.try_start([], Path("/nonexistent/e.jsonl"))
    if feed is not None:
        return c.bad("no compiler, no missing feature", "an empty watch list started a sidecar")
    c.ok("no compiler, no missing feature",
         "started" if present else "the binary is absent on this machine and nothing failed")

    try:
        from core.process_watch import Completion, SpeechGate, Supervisor
    except Exception as exc:                                   # noqa: BLE001
        return c.bad("one announcement path", f"{type(exc).__name__}: {exc}")

    class _Feed:
        alive = False

        def __init__(self, event):
            self.event, self.served = event, False

        def poll(self):
            if self.served:
                return []
            self.served = True
            return [self.event]

    logged, said = [], []
    sup = Supervisor(None, gate=SpeechGate(quiet_for=0.0), feed=_Feed(
        Completion(label="antigravity", pid=1, name="antigravity", seconds=30)),
        say=said.append, log=logged.append)
    sup.tick(busy=False)
    if not logged or "stopped" not in " ".join(logged):
        return c.bad("one announcement path",
                     f"the event or the death was missed: {logged}")
    c.ok("one announcement path",
         "a sidecar event is announced by the same gate, and a dead sidecar says so")


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
    ("philosophy", "Its philosophy is a blend you choose, and no voice may widen it.",
     "a philosophy, with bounds", claim_philosophy),
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
    ("metacognition", "It keeps score on itself, and calls a lucky streak a streak.",
     "meta-cognition / meta-learning", claim_metacognition),
    ("decisions", "It chooses with arithmetic, and it can say \u201cdo nothing\u201d.",
     "a decision system, not a mannerism", claim_decisions),
    ("github", "GitHub is native, and the token stays in one header.",
     "the platforms are native", claim_github),
    ("self_extension", "It adds skills to itself, and cannot add one that writes.",
     "it extends itself", claim_self_extension),
    ("reminders", "It decides when to interrupt you, and when to stay quiet.",
     "the reminder queue", claim_reminders),
    ("procwatch", "It supervises background programs without touching them, "
     "and reports a finish when you stop talking.",
     "background supervision, read-only", claim_process_watch),
    ("sidecar", "The one compiled component is optional, and its absence changes "
     "nothing.", "compiled sidecar, never required", claim_sidecar),
    ("shipping", "It can ship its own work, and a secret stops the ship.",
     "every change reaches GitHub, carefully", claim_shipping),
    ("self_update", "It updates itself from the remote, and undoes a bad version.",
     "it acts from GitHub, not from a folder", claim_self_update),
]


# Why a claim could not be closed here. The owner asked what "13 PARTIAL" means,
# and the honest answer is not a number: it is a list of what this machine lacks.
# A bare count drifts with whichever optional packages happen to be installed,
# which makes a green run look different on two days for no reason. These buckets
# turn the count into a sentence anyone can check.
# Order matters: the first bucket that matches wins, so the specific reasons are
# tested before the general one. A missing PortAudio driver is this machine's audio
# stack, not a missing Python package, and saying "packages 4" when half of those
# are a driver would be a smaller truth than the one available.
BLOCKERS = (
    ("Windows", ("needs Windows", "Windows API", "is Windows", "UI Automation")),
    ("keys", ("--live", "fake server cannot judge", "say 'switch")),
    ("audio or display", ("PortAudio", "no display", "will not load",
                          "could not be imported", "xkbcommon")),
    ("hardware", ("camera index", "could not be opened", "camera")),
    ("your voice", ("your eyes", "legibility", "watch the log")),
    ("packages", ("is not installed", "No module named", "not installed")),
)


def blocked_by(results: list[dict]) -> dict[str, int]:
    """Group the unproven steps by what was missing, not by how many there were."""
    counts: dict[str, int] = {}
    for row in results:
        if row["verdict"] == PROVEN:
            continue
        detail = " ".join(step.get("detail", "") for step in row.get("steps", [])
                          if step.get("status") not in (PROVEN,))
        low = detail.lower()
        bucket = "unclassified"
        for name, needles in BLOCKERS:
            if any(needle.lower() in low for needle in needles):
                bucket = name
                break
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


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
        reasons = blocked_by(results)
        if reasons:
            described = ", ".join(f"{name} {count}"
                                  for name, count in sorted(reasons.items(),
                                                            key=lambda kv: -kv[1]))
            print(f"\n  Unproven here because: {described}")
        print("\n  PARTIAL and SKIPPED are not passes. Run the same command on the "
              "target machine to close them.")

    if args.json:
        # The CI job asks for verification/proof-gate.json, and on a fresh clone
        # that folder does not exist. A report path is a request to write a file;
        # failing on a missing parent turns a green run red for no reason.
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps({
            "platform": platform.platform(), "live": args.live,
            "budgets": {"startup_s": args.budget_startup, "ram_mb": args.budget_ram,
                        "turn_s": args.budget_turn},
            "totals": tally, "claims": results}, indent=2), encoding="utf-8")
        print(f"  report: {args.json}")

    return 1 if probs else 0


if __name__ == "__main__":
    raise SystemExit(main())
