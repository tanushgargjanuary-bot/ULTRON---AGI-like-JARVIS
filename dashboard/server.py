"""
dashboard/server.py — JARVIS Local HTTP Dashboard

Plain HTTP on 127.0.0.1:8000 by default. HTTPS is opt-in (`"dashboard_https": true` in
config/api_keys.json): the first time it is needed a self-signed certificate is generated
for this machine, and its private key is created readable by the owner only. Over HTTPS,
commands are also encrypted with AES-256-GCM under a key derived from the pairing code with
PBKDF2. Over plain HTTP that layer is not available (the browser's `crypto.subtle` needs a
secure context) and commands cross the local network in clear; the page says so on its badge.
The dashboard binds to loopback unless the owner allows LAN access, and LAN access additionally
requires HTTPS. Wrong pairing keys are limited per address on `/login` and `/auto-login`
together.

Install deps:  pip install fastapi "uvicorn[standard]" cryptography
"""

import asyncio
import base64
import hashlib
import re
import secrets
import socket
import string
import threading
import time
from pathlib import Path

from core import failures

_DEPS_OK = False
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    import uvicorn
    _DEPS_OK = True
except ImportError:
    pass

# python-multipart is required for file uploads — optional dependency.
#
# The check is for the PACKAGE. It used to be `from fastapi import UploadFile`,
# which succeeds without it; `_UPLOAD_OK` then said "available", declaring the
# upload route raised RuntimeError("Form data requires python-multipart"), and
# that took the whole dashboard down with it instead of reaching the 503 fallback
# below (reproduced by hiding the package).
def _multipart_installed() -> bool:
    """Is python-multipart importable? (Asked of the package, not of FastAPI.)"""
    try:
        import importlib.util as util
        return (util.find_spec("python_multipart") is not None
                or util.find_spec("multipart") is not None)
    except (ImportError, ValueError):
        return False


_UPLOAD_OK = _multipart_installed()

BASE_DIR    = Path(__file__).resolve().parent.parent
STATIC_DIR  = Path(__file__).parent / "static"
# The port people TYPE, and the port the app actually runs on.
#
# They are not the same, and that is the fix for the most confusing failure
# this dashboard had. A bare `192.168.1.108:8000` typed into a phone browser is
# tried over HTTP; against a TLS listener that means the connection is accepted,
# found to carry no handshake, and closed — which Chrome reports as "refused to
# connect". The server is running perfectly and the user is told it is off.
#
# So the port people reach for answers in the protocol they reach for it with,
# and sends them one hop to the secure one. The QR code carries the secure URL
# directly, so it never takes the hop.
PORT        = 8000      # HTTP, redirects to SECURE_PORT
SECURE_PORT = 8001      # HTTPS, the dashboard itself
MAX_UPLOAD_MB = 500
# A multipart body is the file plus boundary lines and headers. This much more than
# MAX_UPLOAD_MB is allowed to arrive; the exact file size is still enforced below.
_MULTIPART_SLACK_BYTES = 64 * 1024


class _UploadTooLarge(Exception):
    """Raised from the request stream when the body passes the size limit."""


def _safe_filename(raw: str) -> str:
    """A file name that cannot leave the uploads folder or upset the filesystem."""
    name = Path(raw).name                          # strip path components
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(". ")
    return name or "upload"


def _create_unique(dest_dir: Path, safe: str):
    """Create a NEW file named `safe` (or `stem_N.ext`) in `dest_dir` -> (path, handle).

    Exclusive creation, so two uploads of the same name at the same moment cannot
    both open one path and write into each other: the old `while dest.exists()`
    check and the later `open(dest, "wb")` were two steps with a gap between them.
    """
    stem, suffix = Path(safe).stem, Path(safe).suffix
    for counter in range(0, 10_000):
        name = safe if counter == 0 else f"{stem}_{counter}{suffix}"
        try:
            path = dest_dir / name
            return path, open(path, "xb")
        except FileExistsError:
            continue
    raise OSError("could not find a free file name")


async def _store_file(file, dest_dir: Path, max_bytes: int, too_large: tuple):
    """Copy one parsed upload to a new file -> (status, body); removes a partial file."""
    if file is None or not hasattr(file, "read"):
        return 400, {"error": "No file in the request"}
    size = 0
    dest = None
    try:
        dest, fout = _create_unique(dest_dir, _safe_filename(
            getattr(file, "filename", "") or "upload"))
        with fout:
            while size <= max_bytes:
                chunk = await file.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                fout.write(chunk)
    except Exception as exc:                                    # noqa: BLE001
        if dest is not None:
            dest.unlink(missing_ok=True)
        failures.note("dashboard.upload", exc)
        return 500, {"error": str(exc)}
    if size > max_bytes:
        dest.unlink(missing_ok=True)
        return too_large
    return 200, {"ok": True, "name": dest.name, "size": size}


async def _receive_upload(req, dest_dir: Path, max_mb: int):
    """Take ONE uploaded file from a multipart request -> (status, body).

    Called only after the token was checked. The size is bounded as the body streams
    in — by its declared length first, then by counting what actually arrives — so a
    sender cannot make this process read more than `max_mb` plus the multipart
    framing, whatever it declares. FastAPI would otherwise parse the whole body
    before any of our code ran.
    """
    max_bytes = max_mb * 1024 * 1024
    limit = max_bytes + _MULTIPART_SLACK_BYTES
    too_large = (413, {"error": f"File too large (max {max_mb} MB)"})
    declared = req.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        return too_large
    received = 0

    async def capped_receive():
        nonlocal received
        message = await req.receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > limit:
                raise _UploadTooLarge()
        return message

    form = None
    try:
        form = await Request(req.scope, capped_receive).form()
        return await _store_file(form.get("file"), dest_dir, max_bytes, too_large)
    except _UploadTooLarge:
        return too_large
    finally:
        if form is not None:
            await form.close()


def _inside(directory: Path, name: str) -> Path | None:
    """`directory / name` if that is a file directly inside `directory`, else None.

    The download route stripped slashes from the name and joined it. That is not containment:
    on Windows `Path(folder) / "C:secret.txt"` is a drive-relative path that ignores `folder`
    altogether, and `..` and a symlink both lead out. The only check that holds on every
    platform is to resolve the result and look at where it is.
    """
    try:
        root = directory.resolve()
        candidate = (directory / name).resolve()
    except (OSError, ValueError):                 # a NUL byte, an unrepresentable name
        return None
    if candidate.parent != root or not candidate.is_file():
        return None
    return candidate


# The JSON routes carry a pairing key, a device token or one spoken command: well under a
# kilobyte. 64 KB is generous, and it is a cap that exists at all, which the three routes below
# did not have: they read whatever arrived into memory before looking at it.
MAX_JSON_BYTES = 64 * 1024
_BODY_PROBLEMS = {400: "Send a JSON object.", 413: "That request is too large."}


async def _json_object(req) -> tuple[dict | None, int]:
    """The request body as a JSON object, read within MAX_JSON_BYTES -> (object, 200).

    Anything else is a refusal with a status, never an exception: an empty body, bytes that
    are not JSON (the decoder guesses UTF-16 from a NUL byte and fails), JSON that is not an
    object (a list has no `.get`), nesting deep enough to exhaust the parser, a body bigger
    than the cap, a sender that hangs up half way. Each of these used to be an unhandled
    exception, which the server turns into a 500 with a traceback in the log, from a
    stranger, on a route that is reachable before anyone has logged in.
    """
    import json as _json
    declared = req.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_JSON_BYTES:
        return None, 413
    chunks: list[bytes] = []
    size = 0
    try:
        async for chunk in req.stream():
            size += len(chunk)
            if size > MAX_JSON_BYTES:
                return None, 413
            chunks.append(chunk)
    except Exception as exc:                                    # noqa: BLE001
        # ClientDisconnect (the sender left) or a transport error: nothing to answer.
        failures.note("dashboard.json_body", exc)
        return None, 400
    try:
        body = _json.loads(b"".join(chunks))
    except (ValueError, RecursionError):                        # UnicodeDecodeError is a ValueError
        return None, 400
    return (body, 200) if isinstance(body, dict) else (None, 400)


def _make_uploads_dir() -> Path:
    """Return (and create) the cross-platform uploads folder."""
    for candidate in [
        Path.home() / "Downloads" / "JARVIS Uploads",
        Path.home() / "Documents" / "JARVIS Uploads",
        BASE_DIR / "uploads",
    ]:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            pass
    return BASE_DIR / "uploads"


UPLOADS_DIR = _make_uploads_dir()

def _get_gemini_key() -> str | None:
    try:
        import json as _json
        with open(BASE_DIR / "config" / "api_keys.json", "r", encoding="utf-8") as f:
            return _json.load(f).get("gemini_api_key")
    except Exception:
        return None

_KEY_CHARS = [c for c in (string.ascii_uppercase + string.digits)
              if c not in ('O', 'I', 'L', '0', '1')]

# ── AES-256-GCM ───────────────────────────────────────────────────────────────
_AES_SALT = b'JARVIS-DASHBOARD-v1'


# Rounds for the pairing key -> AES key derivation.
#
# WHY THIS IS NOT ONE ROUND OF SHA-256, WHICH IS WHAT IT WAS
#     The pairing key is short because a person has to read it off a screen and
#     type it into a phone. Eight characters from a 31-letter alphabet is about
#     forty bits — fine against someone guessing at the login endpoint, which
#     is rate limited below, and NOT fine against someone who captured one
#     encrypted command and can guess offline as fast as their GPU allows.
#
#     At one round of SHA-256 that offline search is seconds. PBKDF2 at 200k
#     rounds makes each guess about five orders of magnitude more expensive
#     while costing this server ~80 ms once per session, at pairing time, where
#     nobody is waiting on a millisecond.
_KDF_ROUNDS = 200_000


def _derive_key(session_key: str) -> bytes:
    """Pairing key → 32-byte AES-256 key, deliberately slowly. See _KDF_ROUNDS."""
    return hashlib.pbkdf2_hmac(
        "sha256", session_key.encode("utf-8"), _AES_SALT, _KDF_ROUNDS, dklen=32
    )


def _decrypt(aes_key: bytes, enc_b64: str) -> str:
    """Decrypt base64(nonce[12] ‖ ciphertext‖tag) with AES-256-GCM.

    GCM RATHER THAN THE CBC THIS REPLACES
        CBC has no authentication. It hides a message and does nothing to stop
        one being CHANGED: an attacker on the same network can flip bits in the
        ciphertext and the server decrypts whatever falls out, with no way to
        tell. For a channel whose whole purpose is carrying commands to an
        assistant that opens applications and sends messages, "the text was
        secret" is the smaller half of what matters — "the text is the one that
        was sent" is the other half, and CBC never provided it.

        GCM authenticates as it decrypts. A single altered byte raises
        InvalidTag and the request is refused rather than obeyed.

    The old CBC path is not kept as a fallback on purpose. An attacker who can
    choose which format the server accepts can simply choose the weak one, and
    a downgrade left available is a downgrade that will be used.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.b64decode(enc_b64)
    if len(raw) < 13:
        raise ValueError("ciphertext too short to contain a nonce")
    nonce, payload = raw[:12], raw[12:]
    return AESGCM(aes_key).decrypt(nonce, payload, None).decode("utf-8")


_BLOCK_CACHE = None


def blocking_firewall_rules(refresh: bool = False) -> list:
    """Inbound Windows BLOCK rules aimed at the interpreter running this app.

    Public, read-only and never elevated, so the interface can warn about the
    one failure that is invisible from inside the app: a block rule overrides
    every allow rule, so the server listens correctly and the phone still
    cannot reach it. Empty on every other platform and whenever nothing is
    blocked.

    -> [(rule name, program path), ...]

    `refresh=True` ignores the cached answer. The re-check after the elevated
    repair must use it: the cache was filled BEFORE the repair, so without it the
    check read the old list and could only ever answer "still blocked".
    """
    import sys
    if sys.platform != "win32":
        return []

    # Cached for the process. Reading every inbound rule costs about a second,
    # and this is called from the Qt thread when the Remote Control panel
    # opens — a second of frozen interface every time, for an answer that only
    # changes when somebody edits their firewall.
    global _BLOCK_CACHE
    if _BLOCK_CACHE is not None and not refresh:
        return _BLOCK_CACHE
    import os
    import subprocess

    py_exe = sys.executable
    sibling = os.path.join(
        os.path.dirname(py_exe),
        "pythonw.exe" if py_exe.lower().endswith("python.exe") else "python.exe")
    wanted = {py_exe.lower()}
    if os.path.exists(sibling):
        wanted.add(sibling.lower())

    found: list = []
    try:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             "name=all", "dir=in", "verbose"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20,
        )
        name = program = None
        for line in r.stdout.splitlines():
            if line.startswith("Rule Name:"):
                name = line.split(":", 1)[1].strip()
                program = None
            elif line.startswith("Program:"):
                program = line.split(":", 1)[1].strip().lower()
            elif line.startswith("Action:"):
                if (name and program and program in wanted
                        and line.split(":", 1)[1].strip().lower() == "block"
                        and (name, program) not in found):
                    found.append((name, program))
    except Exception as exc:
        print(f"[Dashboard] could not read the firewall rules: {exc}")
    _BLOCK_CACHE = found
    return found


# Characters cmd.exe treats as syntax even inside a .bat line. A rule name is read
# from `netsh` output, i.e. it is whatever the person who created the rule typed,
# and the batch file it goes into runs ELEVATED.
_CMD_SYNTAX = frozenset('"%&|<>^\r\n')


def _split_removable_rules(blocked) -> tuple[list, list]:
    """Split `blocking_firewall_rules()` output into (names the elevated batch may
    delete, names that must be removed by hand).

    `blocked` holds (rule name, program) PAIRS. The batch builder used to loop
    `for rule_name in blocked` and format the pair itself, so it asked Windows to
    delete a rule literally called "('Python (blocked)', 'c:\\python312\\python.exe')"
    — which matches nothing, so the block that made the phone unreachable was
    never removed while the comment above the loop said it was.

    The same rule is listed once per matching program, and `delete rule name=X`
    removes every rule with that name, so each name comes back once.
    """
    removable: list = []
    by_hand: list = []
    for name, _program in blocked:
        bucket = by_hand if any(ch in _CMD_SYNTAX for ch in name) else removable
        if name not in bucket:
            bucket.append(name)
    return removable, by_hand


def _macos_allow_script(fw_ctl: str, py: str) -> str:
    """The AppleScript that lets `py` through the macOS Application Firewall.

    `sys.executable` goes into a shell command inside an AppleScript string. It was
    pasted in unquoted, so an interpreter under a folder with a space in its name
    ("/Users/Ana Ruiz/venv/bin/python") was split into two words by the shell, and a
    quote in the path ended the AppleScript string early. Shell-quote it, then
    escape for AppleScript.
    """
    import shlex
    shell = f"{shlex.quote(fw_ctl)} --add {shlex.quote(py)} && " \
            f"{shlex.quote(fw_ctl)} --unblockapp {shlex.quote(py)}"
    escaped = shell.replace("\\", "\\\\").replace('"', '\\"')
    return f'do shell script "{escaped}" with administrator privileges'


_ACCESS_ASKED = False


def report_network_access(*ports: int) -> bool:
    """Read-only, never elevated: can a phone reach the dashboard? Prints why
    not. Called at startup instead of fixing anything.

    WHY STARTUP NO LONGER FIXES IT
        It used to repair the firewall on every launch, and repairing it needs
        administrator rights — so the app greeted people with Windows' "allow
        this app to make changes to your device?" dialog before it had done
        anything. On a machine where a Windows firewall popup had once been
        cancelled, that block rule came back and so did the dialog, every
        single start. For an open-source app that is the worst first
        impression available: an unexplained request for admin. The repair now
        happens only when somebody opens REMOTE CONTROL — the one feature that
        needs it — where the dialog has an obvious reason.
    """
    import sys
    if sys.platform != "win32":
        return True
    try:
        blocked = blocking_firewall_rules()
    except Exception:
        return True
    if blocked:
        print("[Dashboard] Windows Firewall is blocking this Python from the "
              "network — the phone dashboard will not connect until that is "
              "fixed. Open REMOTE CONTROL to fix it (Windows will ask once).")
        return False
    return True


def fix_network_access(*ports: int) -> None:
    """Make the dashboard reachable from the phone — at most once per run,
    and only because the user asked for the phone dashboard."""
    global _ACCESS_ASKED
    if _ACCESS_ASKED:
        return
    _ACCESS_ASKED = True
    _ensure_network_access(*ports)


def _ensure_network_access(*ports: int) -> None:
    """Cross-platform, best-effort: open port in the OS firewall for LAN access.

    Runs in a background thread. Only ever reached through fix_network_access,
    i.e. from the user opening REMOTE CONTROL — never at startup.

    Windows : writes a .bat file, runs it elevated via Windows ShellExecuteW
              (native UAC dialog, guaranteed to appear). One-time setup.
    macOS   : osascript admin dialog if the Application Firewall is on.
    Linux   : pkexec GUI → sudo -n → prints manual command as fallback.
    """
    import sys
    import subprocess
    import os
    import tempfile
    import threading

    # ── Windows ──────────────────────────────────────────────────────────────
    if sys.platform == "win32":
        import ctypes
        import time

        # Every port in one pass. Called once per port, this asked for
        # elevation once per port — two UAC dialogs for one dashboard, and two
        # racing .bat files whose output interleaved into contradictory
        # messages on the console.
        port_rules = {pt: f"JARVIS Dashboard Port {pt}" for pt in ports}
        prog_rule  = "JARVIS Dashboard Python"

        # BOTH interpreters, because the app runs under either one.
        #
        # THIS IS THE BUG THAT MADE THE PHONE UNREACHABLE FROM THE SHORTCUT.
        #     Started from an editor the app runs under `python.exe`. The
        #     desktop shortcut targets `pythonw.exe`, so that there is no
        #     console window — a different executable, and Windows Firewall
        #     rules are per-executable. Allowing one said nothing about the
        #     other, and the symptom was a dashboard that worked when launched
        #     one way and "refused to connect" when launched the other, on the
        #     same machine and the same network.
        py_exe = sys.executable
        _sibling = os.path.join(os.path.dirname(py_exe),
                                "pythonw.exe" if py_exe.lower().endswith("python.exe")
                                else "python.exe")
        py_exes = [py_exe] + ([_sibling] if os.path.exists(_sibling) else [])

        def _netsh_rule_exists(name: str) -> bool:
            try:
                r = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                )
                return r.returncode == 0 and "No rules match" not in r.stdout
            except Exception:
                return False

        def _network_is_public() -> bool:
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "(Get-NetConnectionProfile | "
                     "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                     "Measure-Object).Count"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=6,
                )
                return r.stdout.strip() not in ("", "0")
            except Exception:
                return False

        # One implementation, at module scope — see blocking_firewall_rules().
        # There were briefly two, and they disagreed about their return type,
        # which surfaced as 'too many values to unpack' in the error path.
        blocked      = blocking_firewall_rules()
        removable, by_hand = _split_removable_rules(blocked)
        missing_ports = [pt for pt, nm in port_rules.items()
                         if not _netsh_rule_exists(nm)]
        need_prog    = not _netsh_rule_exists(prog_rule)
        if _network_is_public():
            print("[Dashboard] This network is set to Public in Windows, which "
                  "blocks phones on it. If it is your own network, set it to "
                  "Private in Settings > Network & internet. JARVIS will not "
                  "change that for you — on public Wi-Fi it would expose this "
                  "computer.")
        need_private = False

        if blocked:
            print(f"[Dashboard] Windows is BLOCKING inbound connections to "
                  f"{', '.join(sorted(set(os.path.basename(e) for e in py_exes)))} "
                  f"({len(blocked)} block rule(s)). Your phone cannot reach the "
                  f"dashboard until those are removed — asking for permission "
                  f"to do that now."
                  + (" Rules whose names contain characters that are not safe in an "
                     "administrator script are left alone — delete them by hand in "
                     "Windows Defender Firewall > Inbound Rules: "
                     + ", ".join(repr(n) for n in by_hand) if by_hand else ""))

        if not missing_ports and not need_prog and not need_private and not blocked:
            return  # already fully configured

        # Build a .bat file — netsh + powershell, runs fast when elevated
        bat_lines = ["@echo off"]
        if need_private:
            bat_lines.append(
                'powershell -NoProfile -NonInteractive -Command "'
                'Get-NetConnectionProfile | '
                "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                'Set-NetConnectionProfile -NetworkCategory Private"'
            )
        for pt in missing_ports:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{port_rules[pt]}" protocol=TCP dir=in '
                f'localport={pt} action=allow'
            )
        # Remove the blocks FIRST. Adding an allow rule beside a block rule
        # changes nothing at all — Windows resolves the conflict in the block's
        # favour — so this is the line that actually fixes the connection.
        for rule_name in removable:
            bat_lines.append(
                f'netsh advfirewall firewall delete rule '
                f'name="{rule_name}" dir=in'
            )

        if need_prog or blocked:
            # One allow rule per interpreter. `add rule` with an existing name
            # appends rather than replacing, so deleting first keeps this from
            # accumulating a new copy on every launch.
            bat_lines.append(
                f'netsh advfirewall firewall delete rule name="{prog_rule}" dir=in'
            )
            for exe in py_exes:
                bat_lines.append(
                    f'netsh advfirewall firewall add rule '
                    f'name="{prog_rule}" dir=in action=allow '
                    f'program="{exe}" enable=yes'
                )

        # Say what will be attempted, so a UAC prompt nobody expected has a
        # reason attached to it in the terminal.
        if blocked:
            print("[Dashboard] The Windows prompt about to appear is JARVIS "
                  "removing those block rules. Declining it leaves the phone "
                  "dashboard unreachable, and nothing else is affected.")

        bat_body = "\r\n".join(bat_lines) + "\r\n"
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="jarvis_fw_")
        try:
            os.write(fd, bat_body.encode("mbcs"))   # Windows cmd.exe expects ANSI
            os.close(fd)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            return

        # ── Try running directly (succeeds when already admin) ────────────────
        try:
            r = subprocess.run(
                [bat_path], capture_output=True, timeout=8, shell=True
            )
            if r.returncode == 0:
                print(f"[Dashboard] Firewall configured for {', '.join(str(pt) for pt in ports)}.")
                try:
                    os.unlink(bat_path)
                except Exception:
                    pass
                return
        except Exception:
            pass

        # ── ShellExecuteW: native UAC elevation (most reliable on Windows) ────
        # ShellExecuteW with verb "runas" always shows the UAC dialog regardless
        # of UAC level settings. Non-blocking — uvicorn is already running.
        print("[Dashboard] One-time network setup required.")
        print("[Dashboard] >>> A Windows security dialog will appear — click 'Yes' <<<")
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,       # hwnd  (no parent window)
                "runas",    # verb  (request elevation)
                bat_path,   # file  (our .bat)
                None,       # params
                None,       # working dir
                0,          # SW_HIDE (run without a visible cmd window)
            )
            if int(ret) > 32:
                # ShellExecuteW returns immediately; bat finishes in ~1 second.
                # Sleep briefly so the rules are in place before the first retry.
                time.sleep(2)
                # CHECK, DO NOT ASSUME. ShellExecuteW succeeding means the
                # dialog was accepted, not that netsh did what was asked — and
                # the whole point of this release is not to report an outcome
                # nobody looked at.
                still = blocking_firewall_rules(refresh=True)
                if still:
                    print("[Dashboard] ⚠️  Windows is STILL blocking inbound "
                          "connections to this interpreter.")
                    print("[Dashboard] ⚠️  Remove these by hand in Windows "
                          "Defender Firewall > Inbound Rules: "
                          + ", ".join(sorted({n for n, _ in still})))
                else:
                    print(f"[Dashboard] Network setup complete — "
                          f"{', '.join(str(pt) for pt in ports)} open.")
                    print("[Dashboard] Refresh your phone browser to connect.")
            else:
                print("[Dashboard] Setup was not allowed.")
                if blocked:
                    print("[Dashboard] Your phone CANNOT reach the dashboard "
                          "until this is done: Windows has block rules for "
                          + ", ".join(sorted({n for n, _ in blocked}))
                          + " which override every allow rule.")
                    print("[Dashboard] Either restart JARVIS and accept the "
                          "prompt, or delete those rules in Windows Defender "
                          "Firewall > Inbound Rules.")
                else:
                    print("[Dashboard] Phone connections may fail until JARVIS "
                          "is run as Administrator.")
        except Exception as e:
            print(f"[Dashboard] Firewall setup error: {e}")
        finally:
            # Cleanup after the bat has had time to run
            def _cleanup(path: str) -> None:
                time.sleep(5)
                try:
                    os.unlink(path)
                except Exception:
                    pass
            threading.Thread(target=_cleanup, args=(bat_path,), daemon=True).start()
        return

    # ── macOS ─────────────────────────────────────────────────────────────────
    if sys.platform == "darwin":
        fw_ctl = "/usr/libexec/ApplicationFirewall/socketfilterfw"
        try:
            r = subprocess.run(
                [fw_ctl, "--getglobalstate"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
            )
            if "disabled" in r.stdout.lower():
                return  # firewall off — nothing to do

            py = sys.executable
            listed = subprocess.run(
                [fw_ctl, "--listapps"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
            )
            if py in listed.stdout:
                return  # already allowed

            print("[Dashboard] One-time network setup — enter your password in the macOS dialog.")
            subprocess.run(
                ["osascript", "-e", _macos_allow_script(fw_ctl, py)],
                timeout=60,
            )
        except Exception:
            pass  # macOS firewall is off by default — silent failure is fine
        return

    # ── Linux ─────────────────────────────────────────────────────────────────
    def _privileged(cmd: list[str]) -> bool:
        for prefix in (["pkexec"], ["sudo", "-n"]):
            try:
                r = subprocess.run(prefix + cmd, capture_output=True, timeout=30)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    # `port` was used here and never defined: the parameter is `*ports`, so every
    # one of these lines raised NameError on any machine whose firewall was
    # actually running. Best-effort and off the main thread, so it failed as a
    # silent no-op — the dashboard stayed unreachable and nothing said why.
    try:  # ufw
        r = subprocess.run(["ufw", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        # "inactive" contains "active", so the old test treated a firewall that
        # was switched OFF as one that needed a rule — and asked for elevation
        # to add it. Ask for the word, not for a substring of its opposite.
        status = " ".join((getattr(r, "stdout", "") or "").split()).lower()
        if "active" in status and "inactive" not in status:
            for port in ports:
                if _privileged(["ufw", "allow", f"{port}/tcp"]):
                    print(f"[Dashboard] ufw: port {port} allowed.")
                else:
                    print(f"[Dashboard] Run manually:  sudo ufw allow {port}/tcp")
            return
    except FileNotFoundError:
        pass

    try:  # firewalld
        r = subprocess.run(
            ["firewall-cmd", "--state"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        )
        if "running" in r.stdout.lower():
            for port in ports:
                ok = (_privileged(["firewall-cmd", "--add-port", f"{port}/tcp", "--permanent"])
                      and _privileged(["firewall-cmd", "--reload"]))
                if ok:
                    print(f"[Dashboard] firewalld: port {port} allowed.")
                else:
                    print(f"[Dashboard] Run manually:  sudo firewall-cmd --add-port={port}/tcp --permanent && sudo firewall-cmd --reload")
            return
    except FileNotFoundError:
        pass

    try:  # iptables (not persistent but works until reboot)
        r = subprocess.run(["iptables", "-L", "INPUT", "-n"], capture_output=True, timeout=5)
        if r.returncode == 0:
            for port in ports:
                if _privileged(["iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"]):
                    print(f"[Dashboard] iptables: port {port} opened.")
                else:
                    print(f"[Dashboard] Run manually:  sudo iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
    except FileNotFoundError:
        pass  # no iptables means firewall is probably off — nothing to do




# ── helpers ───────────────────────────────────────────────────────────────────

def _local_ip() -> str:
    """Return the best LAN-facing IPv4 address, no internet required."""
    # Method 1: route trick (fast, works when internet is available)
    for probe in ("8.8.8.8", "1.1.1.1", "192.168.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                return ip
        except Exception:
            pass

    # Method 2: hostname resolution (works offline on most systems)
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # Method 3: enumerate all interfaces (fully offline, no external deps)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"


def _write_private(path: Path, data: bytes) -> None:
    """Write a secret so that it is never readable by anyone else, not even briefly.

    `write_bytes` then `chmod` leaves a window in which the file exists with the
    process's default mode (0644 on most systems): a private key that any local user
    can read for as long as it takes to reach the next line. Creating the file with
    the mode already set closes the window. Where the platform has no such modes
    (Windows) the flag is accepted and does nothing, as the `chmod` it replaces did.
    """
    import os as _os
    descriptor = _os.open(str(path), _os.O_WRONLY | _os.O_CREAT | _os.O_TRUNC, 0o600)
    with _os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
    try:
        _os.chmod(path, 0o600)    # a file that already existed keeps its old mode otherwise
    except OSError as error:
        failures.note("dashboard._write_private", error, detail=str(path))


def _ensure_certs() -> bool:
    """
    Make sure config/certs holds a TLS key pair, generating a self-signed one the
    first time the dashboard runs.

    The pair is deliberately NOT shipped in the repository. A private key that
    every user downloads is the same as having no private key at all: anyone can
    present a certificate that matches it. Generating locally gives each install
    its own key, costs about a second, and happens exactly once.

    Returns True when a usable pair exists afterwards; False leaves the caller on
    plain HTTP, which still works — the QR code simply encodes http:// instead.
    """
    certs = BASE_DIR / "config" / "certs"
    key_p = certs / "jarvis.key"
    crt_p = certs / "jarvis.crt"
    if key_p.exists() and crt_p.exists():
        return True

    try:
        import datetime
        import ipaddress
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        print("[Dashboard] cryptography not installed — serving over plain HTTP.")
        print("[Dashboard] For HTTPS run:  pip install cryptography")
        return False

    try:
        certs.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        who = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "JARVIS Dashboard"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JARVIS"),
        ])

        # The SAN has to cover every address the phone might use: the LAN IP the
        # QR code encodes, plus localhost when testing on the machine itself.
        alt = [x509.DNSName("localhost"),
               x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
        try:
            lan = _local_ip()
            if not lan.startswith("127."):
                alt.append(x509.IPAddress(ipaddress.IPv4Address(lan)))
        except Exception:
            pass          # no LAN address resolvable — localhost entries still work

        # Timezone-aware UTC: datetime.utcnow() is deprecated from Python 3.12 on,
        # and the builder normalises aware values to UTC itself.
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(who)
            .issuer_name(who)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )

        _write_private(key_p, key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        crt_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

        print(f"[Dashboard] Generated a self-signed certificate for this machine: {certs}")
        return True
    except Exception as e:
        print(f"[Dashboard] Certificate generation failed ({e}) — serving over plain HTTP.")
        return False


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


# ── DashboardServer ───────────────────────────────────────────────────────────

# How long an auth token stays valid, and how many failed logins an address
# gets before it has to wait.
#
# The old code had neither. A token, once issued, worked until the process
# ended — no expiry, no logout — and /login accepted unlimited guesses at the
# pairing key as fast as a script could send them. Eight characters is a large
# space, but "large" is not the same as "let them try forever": the point of a
# limit is that an attacker's cost grows while a person who mistypes their key
# twice never notices it exists.
_TOKEN_TTL_SECONDS = 12 * 3600
_LOGIN_MAX_TRIES   = 6
_LOGIN_WINDOW      = 300.0      # seconds the counter looks back over
_LOGIN_LOCKOUT     = 300.0      # seconds an address waits after using them up
# Addresses remembered at once. A household or a pairing window sees a handful; the number is a
# bound on memory (a few hundred kilobytes), not a target. Without one the table grew with every
# address that ever asked: 100,000 addresses took about 21 MB, and nothing took them out again.
_THROTTLE_MAX_ADDRESSES = 4096


class _Throttle:
    """Failed-attempt counter, per client address.

    Deliberately tiny and in memory: it protects a pairing key that is itself
    only alive for ten minutes, so nothing here needs to survive a restart.
    Successful logins clear the count, which keeps a household on one address
    from locking itself out because somebody fumbled the code once.

    It remembers at most `_THROTTLE_MAX_ADDRESSES` addresses, and only an address that has
    FAILED: asking whether an address is blocked records nothing. (It used to store an empty
    list for every address that asked and never removed it, so the table grew without limit
    even though nobody had failed.) When the table is full it forgets, in this order: addresses
    whose failures are all older than the window, then addresses that are not locked out, oldest
    first. An address that is locked out is the last thing to be forgotten, so filling the table
    with other addresses cannot be used to unlock one.
    """

    def __init__(self):
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked_for(self, who: str) -> float:
        """Seconds this address must wait, or 0."""
        now = time.time()
        with self._lock:
            tries = [t for t in self._fails.get(who, []) if now - t < _LOGIN_WINDOW]
            if tries:
                self._fails[who] = tries
            else:
                self._fails.pop(who, None)      # asking is not failing: keep no row for it
            if len(tries) < _LOGIN_MAX_TRIES:
                return 0.0
            return max(0.0, _LOGIN_LOCKOUT - (now - tries[-1]))

    def record_failure(self, who: str) -> None:
        now = time.time()
        with self._lock:
            tries = self._fails.setdefault(who, [])
            tries.append(now)
            # Only the last few can matter: blocking needs `_LOGIN_MAX_TRIES` of them inside the
            # window and the lockout counts from the latest.
            del tries[:-_LOGIN_MAX_TRIES]
            if len(self._fails) > _THROTTLE_MAX_ADDRESSES:
                self._forget(now)

    def clear(self, who: str) -> None:
        with self._lock:
            self._fails.pop(who, None)

    def _forget(self, now: float) -> None:
        """Make room. The lock is held by the caller."""
        for who in [w for w, tries in self._fails.items()
                    if not tries or now - tries[-1] >= _LOGIN_WINDOW]:
            del self._fails[who]
        if len(self._fails) <= _THROTTLE_MAX_ADDRESSES:
            return
        # Still full of live rows. Go below the limit, not just to it, so the next failure does
        # not do this again: forget the ones that are not locked out first, the oldest first.
        keep = _THROTTLE_MAX_ADDRESSES * 3 // 4
        order = sorted(self._fails, key=lambda w: (len(self._fails[w]) >= _LOGIN_MAX_TRIES,
                                                   self._fails[w][-1]))
        for who in order[:len(self._fails) - keep]:
            del self._fails[who]


class DashboardServer:

    def __init__(self):
        self._ip                          = _local_ip()
        # token -> issued-at. A set had no way to expire anything; this does,
        # and `_auth` sweeps as it reads so nothing has to run a timer.
        self._tokens: dict[str, float]    = {}
        self._token_keys: dict[str, str]  = {}   # auth_token → session_key
        self._aes_cache:  dict[str, bytes]= {}   # session_key → AES bytes
        self._clients: set[WebSocket]     = set()
        self._history: list[dict]         = []
        self._command_queue               = asyncio.Queue()
        self._wake_callback               = None
        self._connect_callback            = None
        self._pending_keys: dict[str, float] = {}
        self._throttle                    = _Throttle()
        self._device_sessions: dict[str, dict] = {}  # device_token → {session_key}
        self._phone_audio_queue: asyncio.Queue    = asyncio.Queue(maxsize=200)
        self._uploads_dir                 = UPLOADS_DIR
        # Set by serve() when the port could not be taken, so the UI can say
        # why the QR code leads nowhere instead of showing it regardless.
        self._bind_error: str = ""
        self._login_html                  = _read("login.html")
        self._app_html                    = _read("app.html")
        self.app                          = self._build_app()

    @staticmethod
    def _allow_lan() -> bool:
        """LAN access is off unless the owner explicitly enables it."""
        try:
            import json as _json
            with open(BASE_DIR / "config" / "api_keys.json", "r",
                      encoding="utf-8") as handle:
                return _json.load(handle).get("dashboard_allow_lan") is True
        except Exception:
            return False

    def _bind_host(self) -> str:
        return "0.0.0.0" if self._allow_lan() and self._ssl_enabled() else "127.0.0.1"

    def _display_host(self) -> str:
        return self._ip if self._allow_lan() and self._ssl_enabled() else "127.0.0.1"

    # ── one-time key management ───────────────────────────────────────────

    def new_key(self, expiry_secs: int = 600) -> str:
        now = time.time()
        self._pending_keys = {k: v for k, v in self._pending_keys.items() if v > now}
        key = ''.join(secrets.choice(_KEY_CHARS) for _ in range(8))
        self._pending_keys[key] = now + expiry_secs
        return key

    @staticmethod
    def _ssl_enabled() -> bool:
        """Is HTTPS switched on? Off unless the user asked for it.

        WHY THE DEFAULT IS PLAIN HTTP, AFTER A RELEASE THAT MADE TLS MANDATORY
            The certificate has to be self-signed — there is no certificate
            authority on earth that will vouch for 192.168.1.108 — and a phone
            treats a self-signed certificate as an attack. Chrome shows a
            full-page interstitial; a QR scanner that opens links in its own
            in-app browser often shows nothing at all and offers no way to
            proceed, because those views deliberately have no "Advanced" button.

            So the practical result of requiring TLS was a dashboard nobody
            could reach, which is not a more secure product than one they can.
            The pairing key, the rate limit, the token expiry and the
            revoke-all-devices fix are all unaffected and all still apply.

            What IS lost over plain HTTP is the AES-GCM layer, because
            `crypto.subtle` does not exist outside a secure context. The page
            says so on its own badge rather than pretending, and commands then
            travel the local network in clear — which is what this dashboard
            did for every release before this one.

            Turn it on with "dashboard_https": true in config/api_keys.json if
            the network is one where that matters; the certificate is generated
            automatically and you will have to accept it once per device.
        """
        try:
            import json as _json
            with open(BASE_DIR / "config" / "api_keys.json", "r",
                      encoding="utf-8") as f:
                if not _json.load(f).get("dashboard_https"):
                    return False
        except Exception:
            return False
        certs = BASE_DIR / "config" / "certs"
        return (certs / "jarvis.key").exists() and (certs / "jarvis.crt").exists()

    def get_url(self) -> str:
        """The full URL the QR code carries — always with its scheme, so a
        scanner never has to guess."""
        host = self._display_host()
        if self._ssl_enabled():
            return f"https://{host}:{SECURE_PORT}"
        return f"http://{host}:{PORT}"

    def get_manual_url(self) -> str:
        """What to type into a phone browser by hand.

        Points at the redirect port when TLS is on, because a bare `ip:port`
        typed into a browser is tried over HTTP — and HTTP against the TLS port
        looks exactly like the server being switched off. The redirector speaks
        HTTP, so it answers, and sends the browser on to the secure page.
        """
        return f"{self._display_host()}:{PORT}"

    def _aes_key(self, session_key: str) -> bytes:
        if session_key not in self._aes_cache:
            self._aes_cache[session_key] = _derive_key(session_key)
        return self._aes_cache[session_key]

    def _decrypt(self, token: str, enc_b64: str) -> str | None:
        sk = self._token_keys.get(token)
        if not sk:
            return None
        try:
            return _decrypt(self._aes_key(sk), enc_b64)
        except Exception:
            return None

    # ── callbacks ────────────────────────────────────────────────────────

    def set_wake_callback(self, fn) -> None:
        self._wake_callback = fn

    def set_connect_callback(self, fn) -> None:
        self._connect_callback = fn

    # ── broadcast ────────────────────────────────────────────────────────

    async def broadcast(self, msg: dict) -> None:
        self._history.append(msg)
        if len(self._history) > 300:
            self._history = self._history[-300:]
        dead: set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    # ── FastAPI app ───────────────────────────────────────────────────────

    def _build_app(self) -> "FastAPI":
        app = FastAPI(docs_url=None, redoc_url=None)

        def _valid(tok: str) -> bool:
            """Is this token live? Expired ones are dropped as they are found,
            which keeps the sweep free and needs no background timer."""
            if not tok:
                return False
            issued = self._tokens.get(tok)
            if issued is None:
                return False
            if time.time() - issued > _TOKEN_TTL_SECONDS:
                self._tokens.pop(tok, None)
                self._token_keys.pop(tok, None)
                return False
            return True

        def _auth(req: Request) -> bool:
            return _valid(req.headers.get("authorization", "")
                          .removeprefix("Bearer ").strip())

        def _who(req: Request) -> str:
            """The client address a throttle counts against."""
            return (getattr(getattr(req, "client", None), "host", "") or "unknown")

        @app.get("/login", response_class=HTMLResponse)
        async def login_page():
            return HTMLResponse(self._login_html)

        @app.get("/", response_class=HTMLResponse)
        async def index():
            # Auth is handled client-side via sessionStorage bearer token.
            # Server-side header auth can't work here because browser navigations
            # don't send custom headers (location.href doesn't carry Authorization).
            html = (self._app_html
                    .replace("__IP__", self._ip)
                    .replace("__PORT__", str(PORT)))
            return HTMLResponse(html)

        @app.post("/login")
        async def login(req: Request):
            who  = _who(req)
            wait = self._throttle.blocked_for(who)
            if wait > 0:
                # 429 rather than 401 on purpose: it tells an honest user why
                # their correct key was refused, and it tells a script that
                # guessing is not working.
                return JSONResponse(
                    {"ok": False,
                     "error": f"Too many attempts. Try again in "
                              f"{int(wait) + 1} seconds."},
                    status_code=429,
                )
            body, problem = await _json_object(req)
            if body is None:
                # A request that is not a login attempt still costs one, or malformed
                # bodies would be a way to hammer this route for free.
                self._throttle.record_failure(who)
                return JSONResponse({"ok": False, "error": _BODY_PROBLEMS[problem]},
                                    status_code=problem)
            entered = str(body.get("pin", "")).strip().upper()
            now     = time.time()
            if entered in self._pending_keys and self._pending_keys[entered] > now:
                self._throttle.clear(who)
                del self._pending_keys[entered]          # one-time use
                tok = secrets.token_urlsafe(32)
                self._tokens[tok] = time.time()
                self._token_keys[tok] = entered
                self._aes_key(entered)                   # pre-derive & cache
                if self._connect_callback:
                    self._connect_callback()
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Remote connection established."}
                ))
                # Bearer token in response body — no cookies needed (works on any browser/HTTP)
                return JSONResponse({"ok": True, "token": tok})
            self._throttle.record_failure(who)
            return JSONResponse({"ok": False, "error": "Invalid or expired key"},
                                status_code=401)

        @app.get("/auto-login")
        async def auto_login(req: Request, key: str = ""):
            """QR code target — validates one-time key, creates session, redirects phone.

            Counted against the same per-address throttle as `/login`: this route takes
            the same pairing key, and a guess here was free while a guess there was
            limited, so the limit only protected the door nobody had to use.
            """
            who  = _who(req)
            wait = self._throttle.blocked_for(who)
            if wait > 0:
                return HTMLResponse(
                    f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width"></head>
<body style="background:#07090f;color:#dde3ed;font-family:sans-serif;text-align:center;padding-top:30vh">
<h2 style="color:#f87171">Too many attempts</h2>
<p>Try again in {int(wait) + 1} seconds.</p></body></html>""",
                    status_code=429)
            now = time.time()
            if not key or key not in self._pending_keys or self._pending_keys[key] <= now:
                self._throttle.record_failure(who)
                return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
  h2{color:#f87171;margin-bottom:12px}p{color:#5e6a7e;font-size:14px}
</style></head>
<body><div><h2>Link Expired</h2>
<p>Press <strong style="color:#dde3ed">Remote Control</strong> in JARVIS to get a new QR code.</p>
</div></body></html>""")

            self._throttle.clear(who)
            del self._pending_keys[key]
            tok     = secrets.token_urlsafe(32)
            dev_tok = secrets.token_urlsafe(32)
            self._tokens[tok] = time.time()
            self._token_keys[tok] = key
            self._aes_key(key)
            self._device_sessions[dev_tok] = {"session_key": key}

            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Remote connection established via QR code."}
            ))

            return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
  p{{color:#5e6a7e;font-size:14px}}
</style></head>
<body>
<script>
  sessionStorage.setItem('jarvis_token','{tok}');
  sessionStorage.setItem('jarvis_key','{key}');
  localStorage.setItem('jarvis_device_token','{dev_tok}');
  setTimeout(function(){{location.replace('/')}},400);
</script>
<p>Connecting to JARVIS…</p>
</body></html>""")

        @app.post("/api/device-login")
        async def device_login_ep(req: Request):
            """Return a fresh auth token for a previously paired device token."""
            body, problem = await _json_object(req)
            if body is None:
                return JSONResponse({"ok": False, "error": _BODY_PROBLEMS[problem]},
                                    status_code=problem)
            dev_tok = body.get("device_token")
            dev_tok = dev_tok.strip() if isinstance(dev_tok, str) else ""
            if not dev_tok or dev_tok not in self._device_sessions:
                return JSONResponse({"ok": False}, status_code=401)
            session_key = self._device_sessions[dev_tok]["session_key"]
            tok = secrets.token_urlsafe(32)
            self._tokens[tok] = time.time()
            self._token_keys[tok] = session_key
            self._aes_key(session_key)
            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Known device reconnected automatically."}
            ))
            return JSONResponse({"ok": True, "token": tok, "key": session_key})

        @app.post("/api/revoke-devices")
        async def revoke_devices(req: Request):
            """Invalidate all persistent device tokens (admin action)."""
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            # ALSO drop the live tokens, which this did not do.
            #
            # It cleared the remembered devices and left every session those
            # devices had already opened working until the app restarted — so
            # "revoke all devices" revoked nothing anybody was currently using,
            # which is the one case somebody presses it for.
            #
            # The caller's own token is kept, or pressing the button would log
            # out the person who pressed it.
            mine  = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            count = len(self._device_sessions)
            live  = len(self._tokens) - (1 if mine in self._tokens else 0)
            self._device_sessions.clear()
            keep = self._tokens.get(mine)
            self._tokens.clear()
            self._token_keys = {k: v for k, v in self._token_keys.items() if k == mine}
            if keep is not None:
                self._tokens[mine] = keep
            return JSONResponse({"ok": True, "revoked": count, "sessions_ended": live})

        @app.post("/api/command")
        async def command(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body, problem = await _json_object(req)
            if body is None:
                return JSONResponse({"error": _BODY_PROBLEMS[problem]}, status_code=problem)
            token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            enc   = body.get("enc") or ""
            sent  = body.get("text") or ""
            if not isinstance(enc, str) or not isinstance(sent, str):
                return JSONResponse({"error": "`text` and `enc` must be strings."},
                                    status_code=400)
            if enc:
                text = self._decrypt(token, enc)
                if text is None:
                    return JSONResponse({"error": "Decryption failed"}, status_code=400)
            else:
                text = sent.strip()
            if text:
                await self._command_queue.put(text)
                if self._wake_callback:
                    self._wake_callback()
            return JSONResponse({"ok": True})

        @app.post("/api/wake")
        async def wake_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            if self._wake_callback:
                self._wake_callback()
            return JSONResponse({"ok": True})

        # ── Phone mic real-time audio → Gemini Live ──────────────────────────

        @app.websocket("/ws/phone-audio")
        async def phone_audio_ws(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not _valid(tok):
                await websocket.close(code=4001)
                return
            await websocket.accept()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Phone microphone live."}
            ))
            ignored = 0               # text frames on the audio socket, noted once at the end
            try:
                while True:
                    try:
                        data = await websocket.receive_bytes()
                    except KeyError:
                        ignored += 1      # a text frame: not audio
                        continue
                    try:
                        self._phone_audio_queue.put_nowait(
                            {"data": data, "mime_type": "audio/pcm"}
                        )
                    except asyncio.QueueFull:
                        pass  # drop frame rather than block
            except WebSocketDisconnect:
                pass
            finally:
                if ignored:
                    failures.note("dashboard.phone_audio", f"ignored {ignored} text frame(s)")
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Phone microphone stopped."}
                ))

        # ── File sharing ──────────────────────────────────────────────────────

        if _UPLOAD_OK:
            @app.post("/api/upload")
            async def upload_file(req: Request):
                # Authenticate BEFORE any of the body is read. The route used to
                # declare `file: UploadFile`, so FastAPI parsed and spooled the whole
                # multipart body first, and a stranger's 40 MB was accepted before
                # the 401 (measured). With no body parameter this function is called
                # first, and `_receive_upload` parses the form through a bounded read.
                if not _auth(req):
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)
                status, body = await _receive_upload(req, self._uploads_dir,
                                                     MAX_UPLOAD_MB)
                if status == 200:
                    asyncio.create_task(self.broadcast({
                        "type": "file_received",
                        "name": body["name"],
                        "size": body["size"],
                        "saved_to": str(self._uploads_dir),
                    }))
                return JSONResponse(body, status_code=status)
        else:
            @app.post("/api/upload")
            async def upload_unavailable(req: Request):
                return JSONResponse(
                    {"error": "File uploads require: pip install python-multipart"},
                    status_code=503,
                )

        @app.get("/api/files")
        async def list_files(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            files = []
            try:
                for f in sorted(
                    (p for p in self._uploads_dir.iterdir() if p.is_file()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    files.append({"name": f.name, "size": f.stat().st_size})
            except Exception:
                pass
            return JSONResponse({"files": files})

        @app.get("/uploads/{filename}")
        async def download_file(filename: str, token: str = ""):
            # Auth via query param — browser <a download> can't send custom headers
            tok = token.strip()
            if not _valid(tok):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            safe = re.sub(r'[/\\]', '', filename)
            path = _inside(self._uploads_dir, safe)
            if path is None:
                return JSONResponse({"error": "Not found"}, status_code=404)
            return FileResponse(str(path), filename=path.name)

        @app.websocket("/ws")
        async def ws_ep(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not _valid(tok):
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._clients.add(websocket)
            for entry in self._history[-50:]:
                try:
                    await websocket.send_json(entry)
                except Exception:
                    break
            ignored = 0               # malformed frames, noted once when the socket closes
            try:
                while True:
                    try:
                        data = await websocket.receive_json()
                    except (ValueError, KeyError):
                        ignored += 1      # not JSON, or a binary frame: keep the socket
                        continue
                    if not isinstance(data, dict):
                        ignored += 1      # a list, a number, a string
                        continue
                    if data.get("type") != "command":
                        continue          # some other kind of message: not ours to answer
                    enc  = data.get("enc") or ""
                    sent = data.get("text") or ""
                    if not isinstance(enc, str) or not isinstance(sent, str):
                        ignored += 1
                        continue
                    t = self._decrypt(tok, enc) if enc else sent.strip()
                    if t:
                        await self._command_queue.put(t)
                        if self._wake_callback:
                            self._wake_callback()
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(websocket)
                if ignored:
                    failures.note("dashboard.ws", f"ignored {ignored} malformed frame(s)")

        return app

    # ── serve ─────────────────────────────────────────────────────────────

    async def _serve_redirector(self) -> None:
        """A plain-HTTP listener whose only job is to send people to HTTPS.

        THE PROBLEM THIS SOLVES, WHICH LOOKED LIKE THE SERVER BEING DOWN
            Type `192.168.1.108:8000` into a phone browser and it tries HTTP.
            The TLS server accepts the connection, finds no handshake and
            closes it — which Chrome reports as "This site can't be reached,
            192.168.1.108 refused to connect". The server is running perfectly
            and the user is told it is off.

            The port that used to sit here was a SECOND HTTPS server, added on
            the belief that browsers upgrade a bare `ip:port` to https. Some
            do. Android Chrome does not, so the second port had exactly the
            same failure as the first.

        So this speaks HTTP, and answers everything with a redirect to the same
        path on the HTTPS port. Typing the address by hand now works, which is
        what people do when a QR code is inconvenient.
        """
        from fastapi.responses import RedirectResponse

        bounce = FastAPI(docs_url=None, redoc_url=None)

        @bounce.get("/{path:path}")
        async def _to_https(path: str, request: Request):
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(
                f"https://{self._display_host()}:{SECURE_PORT}/{path}{query}",
                status_code=307)

        cfg = uvicorn.Config(bounce, host=self._bind_host(), port=PORT,
                             log_level="warning")
        print(f"[Dashboard] Type by hand:  {self._display_host()}:{PORT}  "
              f"(sends you to the secure page)")
        await uvicorn.Server(cfg).serve()

    async def serve(self) -> None:
        if not _DEPS_OK:
            print("[Dashboard] fastapi/uvicorn not installed — dashboard disabled.")
            print("[Dashboard] Run:  pip install fastapi 'uvicorn[standard]' cryptography")
            return

        allow_lan = self._allow_lan()

        # Only make a certificate if HTTPS was actually asked for. Generating
        # one nobody uses just leaves a private key on disk.
        try:
            import json as _json
            with open(BASE_DIR / "config" / "api_keys.json", "r",
                      encoding="utf-8") as f:
                if _json.load(f).get("dashboard_https"):
                    _ensure_certs()
        except Exception:
            pass

        use_ssl  = self._ssl_enabled()
        ssl_key  = BASE_DIR / "config" / "certs" / "jarvis.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "jarvis.crt"

        # Cert creation runs first, so a first-time HTTPS opt-in can work.
        # An incomplete or failed certificate setup must never expose LAN commands.
        if allow_lan and not use_ssl:
            print("[Dashboard] LAN access refused: dashboard_https must be true and "
                  "a valid local certificate must exist before dashboard_allow_lan.")
            return
        if allow_lan:
            asyncio.get_running_loop().run_in_executor(
                None, report_network_access, PORT, SECURE_PORT)

        # TLS IS WANTED, BUT NOT AT THE COST OF NOT STARTING.
        #
        # An earlier version returned here when certificates could not be made,
        # on the argument that serving a remote-control channel in clear is a
        # different product. The argument is right and the behaviour was wrong:
        # a dashboard that does not start is not more secure, it is absent, and
        # the user is left with "refused to connect" and nothing to act on.
        #
        # So: HTTPS whenever it can be had — which is almost always, since the
        # certificate is generated locally on first run — and plain HTTP with a
        # loud, repeated warning when it cannot. The page keeps working either
        # way; without a secure context it simply cannot encrypt, and it says
        # so on screen rather than pretending.
        if use_ssl:
            asyncio.create_task(self._serve_redirector())
        elif allow_lan:
            failures.note("dashboard.lan_refused", "Refused an unencrypted LAN command listener.")
            return
        else:
            failures.note(
                "dashboard.loopback_only",
                'HTTP is available on loopback. Set dashboard_https=true and '
                'dashboard_allow_lan=true for remote access.',
            )

        cfg = uvicorn.Config(
            self.app, host=self._bind_host(),
            port=SECURE_PORT if use_ssl else PORT, log_level="warning",
            **({"ssl_keyfile": str(ssl_key), "ssl_certfile": str(ssl_cert)}
               if use_ssl else {}),
        )

        # CAN THIS PORT ACTUALLY BE TAKEN?
        #
        # uvicorn raises when the port is busy, and under pythonw.exe there is
        # no console for that to be seen in — so a second JARVIS, or anything
        # else already on 8000, produced a dashboard that was silently dead
        # while the HUD went on showing a QR code pointing at it. The phone
        # then reports ERR_CONNECTION_REFUSED, which is true and impossible to
        # act on.
        #
        # Asking first costs a millisecond and turns that into a sentence.
        import socket as _socket
        # No SO_REUSEADDR. On Windows that option lets a second socket bind a
        # port another socket already holds — which is exactly the condition
        # being tested for, so setting it made the probe always succeed.
        _probe = _socket.socket()
        try:
            _probe.bind((self._bind_host(), SECURE_PORT if use_ssl else PORT))
        except OSError as exc:
            _probe.close()
            self._bind_error = (
                f"port {SECURE_PORT if use_ssl else PORT} on {self._bind_host()} is already in use — "
                f"another copy of JARVIS is probably running. Close it and "
                f"restart, or the phone dashboard will stay unreachable "
                f"({exc.__class__.__name__})")
            print(f"[Dashboard] {self._bind_error}")
            return
        _probe.close()

        print(f"[Dashboard] {self.get_url()}")
        print("[Dashboard] Press 'Remote Control' in JARVIS UI to get the QR code.")
        await uvicorn.Server(cfg).serve()
