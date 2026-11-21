import os
import re
import shutil
import platform
from pathlib import Path
from datetime import datetime

try:
    import send2trash
    _SEND2TRASH = True
except ImportError:
    _SEND2TRASH = False

from core import failures
from core.undo import push_undo

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# Undo keeps a file's previous contents in memory so `write` can be reversed.
# Above this size it does not — a 200 MB log would sit in RAM for the rest of
# the session to protect an edit nobody is going to take back.
_UNDO_CONTENT_LIMIT = 1_000_000


def _undo_move(src: Path, dst: Path):
    """Reverse of a move: put it back where it came from."""
    def _fn():
        if not dst.exists():
            return f"'{dst.name}' is no longer there — nothing moved back."
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(src))
        return f"'{src.name}' is back in {src.parent.name}/."
    return _fn


def _undo_create(target: Path):
    """Reverse of a create: remove what we made — and only if we still made it.

    Deliberately refuses to touch a directory that has since been filled: the
    undo for 'create a folder' is not 'delete whatever ended up in it'."""
    def _fn():
        if not target.exists():
            return f"'{target.name}' is already gone."
        if target.is_dir():
            if any(target.iterdir()):
                return (f"'{target.name}' is not empty any more — "
                        f"leaving it alone rather than deleting your files.")
            target.rmdir()
        else:
            target.unlink()
        return f"Removed '{target.name}'."
    return _fn


def _undo_write(target: Path, previous: str | None):
    """Reverse of a write: restore the old contents, or remove a file that did
    not exist before the write created it."""
    def _fn():
        if previous is None:
            if target.exists():
                target.unlink()
                return f"Removed '{target.name}' — it did not exist before."
            return f"'{target.name}' is already gone."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(previous, encoding="utf-8")
        return f"Restored the previous contents of '{target.name}'."
    return _fn


def _restore_from_trash(original: Path) -> str:
    """Best-effort undelete.

    delete_file uses send2trash, which is the right call: the file lands in the
    Recycle Bin / Trash where the person can also find it themselves. Getting it
    back out again is shell work and only reliable on Windows, where pywin32 is
    already a dependency. Everywhere else this says where the file is instead of
    pretending it failed — the file is not lost either way."""
    if _OS == "Windows":
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            bin_folder = shell.NameSpace(10)      # ssfBITBUCKET
            for item in bin_folder.Items():
                if str(bin_folder.GetDetailsOf(item, 1)).strip().lower() == \
                        str(original.parent).strip().lower():
                    if str(item.Name).strip().lower() == original.name.strip().lower():
                        item.InvokeVerb("UNDELETE")
                        return f"'{original.name}' restored from the Recycle Bin."
        except Exception as e:
            print(f"[file] Recycle Bin restore failed: {e}")
    return (f"'{original.name}' is in the Recycle Bin — I could not pull it back "
            f"automatically, but it is there and can be restored by hand.")


_SAFE_ROOTS: list[Path] = [
    Path.home(),
]

# ── the parts of home that are not "your files" ──────────────────────────────
#
# "Inside the home directory" was the whole safety test, and home is where every
# credential on the machine lives. Measured before this was added: reading
# `~/.ssh/id_rsa` was allowed, and so was reading this program's own
# `config/api_keys.json` — the latter read out loud into an activity log by a
# model that had been talked into it by a web page.
#
# A deny-list rather than an allow-list because the useful case is "the files I
# put in my own folders", which has no fixed shape. Denying by directory name and
# by file name costs the user nothing they were going to ask for, and a refusal
# that names the reason is something they can act on.
# EVERY entry is lower-case and uses "/": the path it is compared with is lowered
# and slash-normalised first. `.config/BraveSoftware` used to sit here in mixed case,
# so it could never match anything — the Brave profile, which holds saved logins,
# was readable while the owner's own list said browser profiles were not.
#
# An entry matches where it starts a path component and is not the front of a longer
# name: `.ssh`, `.ssh/id_rsa` and `.ssh-old` match; `.dockerignore` does not match
# `.docker` (a project file nobody means as a credential store, refused as one).
_SENSITIVE_DIR_PARTS = (
    ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store",
    ".local/share/keyrings", ".config/gcloud", ".config/gh", ".config/rclone",
    ".thunderbird", ".git/config",          # a remote URL in .git/config can hold a token
    "appdata/roaming/microsoft/credentials", "appdata/roaming/microsoft/protect",
    "appdata/local/microsoft/credentials", "appdata/roaming/github cli",
    "appdata/roaming/rclone", "appdata/roaming/thunderbird",
    # browser profiles: saved logins, cookies, tokens
    "google/chrome/user data", "microsoft/edge/user data",
    "bravesoftware/brave-browser/user data", "vivaldi/user data",
    "opera software", "mozilla/firefox/profiles", ".mozilla",
    ".config/google-chrome", ".config/chromium", ".config/microsoft-edge",
    ".config/bravesoftware", ".config/vivaldi", ".config/opera",
    # macOS
    "library/keychains", "library/application support/google/chrome",
    "library/application support/firefox", "library/application support/microsoft edge",
    "library/application support/bravesoftware",
)
_SENSITIVE_FILE_NAMES = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "api_keys.json",
    ".env", ".netrc", ".git-credentials", ".pgpass", "credentials",
    "login data", "cookies", "key4.db", "logins.json", "wallet.dat", "ntds.dit",
    "secrets.json", "secret.json",
    # tokens and passwords that live in a plain file
    ".npmrc", ".pypirc", ".yarnrc", ".yarnrc.yml", ".dockercfg", ".s3cfg", ".boto",
    ".my.cnf", ".vault-token", ".htpasswd", "rclone.conf", "kubeconfig",
    "terraform.tfstate", "terraform.tfstate.backup",
    # shell histories collect whatever was pasted into a terminal, tokens included
    ".bash_history", ".zsh_history", ".python_history", ".mysql_history",
    ".psql_history", ".node_repl_history", "consolehost_history.txt",
}
_SENSITIVE_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".kdbx", ".kdb", ".keystore",
                       ".jks", ".ppk", ".ovpn", ".p8")
# `id_rsa_work`, `id_ed25519.bak` — a copy of a private key is still one. The public
# half (`.pub`) is meant to be shared and is left alone.
_SENSITIVE_NAME_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")
_CRITICAL_SYSTEM_DIR_PARTS = (
    "windows/system32", "windows/syswow64", "windows/winsxs",
    "$recycle.bin", "system volume information",
)


def _parts_regex(parts) -> "re.Pattern":
    """One compiled test for a tuple of path fragments (see the note above)."""
    return re.compile(r"(?:^|/)(?:" + "|".join(re.escape(part) for part in parts)
                      + r")(?![a-z0-9])")


_SENSITIVE_DIR_RE = _parts_regex(_SENSITIVE_DIR_PARTS)
_CRITICAL_DIR_RE = _parts_regex(_CRITICAL_SYSTEM_DIR_PARTS)


def _as_posix_lower(target: Path) -> str:
    try:
        text = str(target.resolve())
    except Exception:
        text = str(target)
    return text.replace("\\", "/").lower()


def _is_sensitive(target: Path) -> bool:
    """True for credential stores, system critical folders, and anything nobody means by 'a file'."""
    text = _as_posix_lower(target)
    if _CRITICAL_DIR_RE.search(text) or _SENSITIVE_DIR_RE.search(text):
        return True
    name = target.name.lower()
    if name in _SENSITIVE_FILE_NAMES:
        return True
    if name.startswith(".env.") or name.startswith("credentials."):
        return True
    if name.startswith(_SENSITIVE_NAME_PREFIXES) and not name.endswith(".pub"):
        return True
    return name.endswith(_SENSITIVE_SUFFIXES)


def _denial_message(target: Path) -> str:
    """Why this path was refused, in words the user can act on.

    "Access denied" for a file the assistant simply will not read looks like a
    permissions problem, and sends people looking for one. A credential store is
    a different answer and deserves saying.
    """
    text = _as_posix_lower(target)
    if _CRITICAL_DIR_RE.search(text):
        return (f"I will not touch {target.name} — it is a critical operating system directory.")
    if _is_sensitive(target):
        return (f"I will not touch {target.name} — it holds credentials. "
                f"Open it yourself if you need what is in it.")
    return f"Access denied: {target}"


def _configured_roots(cfg: dict) -> list[Path]:
    """The folders the owner listed in `allowed_roots` that exist."""
    raw = cfg.get("allowed_roots", [])
    if not isinstance(raw, (list, tuple)):
        failures.note("file_controller.roots",
                      f"allowed_roots must be a list, not {type(raw).__name__}")
        return []
    found: list[Path] = []
    for custom_path in raw:
        try:
            resolved = Path(custom_path).resolve()
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            failures.note("file_controller.roots", error, detail=str(custom_path))
            continue
        if resolved.exists() and resolved not in found:
            found.append(resolved)
    return found


def _get_laptop_roots() -> list[Path]:
    """Retrieve allowed roots including configured roots and user partitions."""
    roots = list(_SAFE_ROOTS)
    try:
        from memory.config_manager import load_api_keys
        cfg = load_api_keys()
    except Exception as error:                                  # noqa: BLE001
        failures.note("file_controller.roots", error)
        return roots
    for path in _configured_roots(cfg):
        if path not in roots:
            roots.append(path)
    # Enable multi-drive laptop access by default on Windows or when configured
    if cfg.get("laptop_wide_access", True) and _OS == "Windows":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{letter}:/")
            if drive.exists() and drive not in roots:
                roots.append(drive)
    return roots


def _is_safe_path(target: Path) -> bool:
    """Is the given path inside _SAFE_ROOTS (or laptop roots) and not a credential/system store?

    Known user folders (Downloads, Documents, ...) count as safe roots too.
    OneDrive and others redirect them outside the home folder (for example
    `~/Downloads` resolves to `D:/Downloads`). The credential check runs
    first, so a file inside those folders is still refused when it is a
    credential store.
    """
    # NTFS alternate data streams use a colon after the file name
    # (for example, report.txt:secret). They are not ordinary files and must
    # not bypass the workspace path policy.
    if _OS == "Windows" and ":" in target.name:
        return False
    try:
        resolved = target.resolve()
        if _is_sensitive(resolved):
            return False
        roots = _get_laptop_roots()
        # `_get_*` are defined below; resolve them lazily so this check
        # stays cheap and keeps working if a folder is redirected.
        for helper in (_get_desktop, _get_downloads, _get_documents,
                       _get_pictures, _get_music, _get_videos):
            try:
                path = helper()
            except Exception as error:                          # noqa: BLE001
                failures.note("file_controller.folders", error, detail=helper.__name__)
                continue
            if path not in roots:
                roots.append(path)
        return any(
            resolved == root.resolve() or resolved.is_relative_to(root.resolve())
            for root in roots
        )
    except Exception:
        return False

def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Desktop"

def _get_downloads() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOWNLOAD_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Downloads"

def _get_documents() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOCUMENTS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Documents"

def _get_pictures() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_PICTURES_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Pictures"

def _get_music() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_MUSIC_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Music"

def _get_videos() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_VIDEOS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Videos"


def _resolve_path(raw: str) -> Path:
    shortcuts: dict[str, Path] = {
        "desktop":   _get_desktop(),
        "downloads": _get_downloads(),
        "documents": _get_documents(),
        "pictures":  _get_pictures(),
        "music":     _get_music(),
        "videos":    _get_videos(),
        "home":      Path.home(),
    }
    if _OS == "Windows":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{letter}:/")
            if drive.exists():
                shortcuts[f"{letter.lower()}:"] = drive
                shortcuts[f"drive_{letter.lower()}"] = drive
                shortcuts[f"{letter.lower()}_drive"] = drive

    raw = raw.strip().strip('"').strip("'")
    if _OS == "Windows":
        # "d:" or "D:" -> Path("D:/")
        if re.match(r"^[A-Za-z]:[\\/]?$", raw):
            return Path(f"{raw[0].upper()}:/")
        # "d:notes" -> Path("D:/notes")
        if re.match(r"^[A-Za-z]:[^\\/]", raw):
            return Path(f"{raw[0].upper()}:/{raw[2:]}")

    lower = raw.lower()
    if lower in shortcuts:
        return shortcuts[lower]

    # "desktop/notes/a.md" and "desktop\notes\a.md" — a shortcut followed by a
    # sub-path.  Without this branch the whole string falls through to the
    # relative-path return below and is resolved against the process CWD instead
    # of the real Desktop: an "Access denied" when the project lives outside the
    # home directory, or — worse — a silent write into a stray "desktop" folder
    # inside the project when it lives inside it.
    head, sep, rest = raw.replace("\\", "/").partition("/")
    if sep and head.lower() in shortcuts:
        rest = rest.strip("/")
        return shortcuts[head.lower()] / rest if rest else shortcuts[head.lower()]

    return Path(raw).expanduser()

def _format_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def _safe_trash(target: Path) -> str:

    if not _SEND2TRASH:
        return (
            "send2trash is not installed. "
            "Run: pip install send2trash — "
            "Permanent deletion is disabled for safety."
        )
    send2trash.send2trash(str(target))
    return f"Moved to Trash: {target.name}"


def list_files(path: str = "desktop", show_hidden: bool = False) -> str:
    try:
        target = _resolve_path(path)
        if not _is_safe_path(target):
            return _denial_message(target)
        if not target.exists():
            return f"Path not found: {target}"
        if not target.is_dir():
            return f"Not a directory: {target}"

        items = []
        for item in sorted(target.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = _format_size(item.stat().st_size)
                items.append(f"📄 {item.name} ({size})")

        if not items:
            return f"Directory is empty: {target.name}/"

        return f"Contents of {target.name}/ ({len(items)} items):\n" + "\n".join(items)

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error listing files: {e}"


def create_file(path: str, name: str = "", content: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _denial_message(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        previous = None
        if existed:
            try:
                previous = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                previous = None
        target.write_text(content, encoding="utf-8")
        push_undo(f"created {target.name}",
                  _undo_write(target, previous) if existed else _undo_create(target))
        return f"File created: {target.name}"
    except Exception as e:
        return f"Could not create file: {e}"


def create_folder(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _denial_message(target)
        already = target.exists()
        target.mkdir(parents=True, exist_ok=True)
        # Only offer to undo a folder we actually made. "mkdir -p" on something
        # that was already there is not a change, and undoing it would delete a
        # directory the user has had for years.
        if not already:
            push_undo(f"created folder {target.name}", _undo_create(target))
        return f"Folder created: {target.name}"
    except Exception as e:
        return f"Could not create folder: {e}"


def delete_file(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _denial_message(target)
        if not target.exists():
            return f"Not found: {target.name}"

        # Safe-directory check — protect critical user folders
        protected = {
            _get_desktop(), _get_downloads(), _get_documents(),
            _get_pictures(), _get_music(), _get_videos(), Path.home()
        }
        if target.resolve() in {p.resolve() for p in protected}:
            return f"Protected directory, cannot delete: {target.name}"

        original = target.resolve()
        result   = _safe_trash(target)
        if result.startswith("Moved to Trash"):
            push_undo(f"deleted {original.name}",
                      lambda p=original: _restore_from_trash(p))
        return result

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Could not delete: {e}"


def move_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base   = _resolve_path(path)
        src    = (base / name) if name else base
        dst    = _resolve_path(destination) if destination else None

        if not src.exists():
            return f"Source not found: {src.name}"
        if dst is None:
            return "No destination specified."
        if not _is_safe_path(src):
            return "Source refused: " + _denial_message(src)
        if not _is_safe_path(dst):
            return "Destination refused: " + _denial_message(dst)

        if dst.is_dir():
            dst = dst / src.name

        # Refuse rather than replace. `shutil.move` onto an existing file replaces
        # it, and the undo this registers moves the NEW file back — so the file that
        # was overwritten was gone for good. `rename_file` already refuses.
        if dst.exists():
            return (f"'{dst.name}' already exists in {dst.parent.name}/ — nothing was "
                    f"moved. Rename or remove one of them first.")

        dst.parent.mkdir(parents=True, exist_ok=True)
        origin = src.resolve()
        shutil.move(str(src), str(dst))
        push_undo(f"moved {origin.name} to {dst.parent.name}/",
                  _undo_move(origin, dst.resolve()))
        return f"Moved: {src.name} → {dst.parent.name}/"

    except Exception as e:
        return f"Could not move: {e}"


def copy_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base = _resolve_path(path)
        src  = (base / name) if name else base
        dst  = _resolve_path(destination) if destination else None

        if not src.exists():
            return f"Source not found: {src.name}"
        if dst is None:
            return "No destination specified."
        if not _is_safe_path(src):
            return "Source refused: " + _denial_message(src)
        if not _is_safe_path(dst):
            return "Destination refused: " + _denial_message(dst)

        if dst.is_dir():
            dst = dst / src.name

        # Refuse rather than replace. `copy2` onto an existing file overwrites it, and
        # the undo below deletes the destination — so undoing an overwriting copy
        # removed the file that had been there first, with no way back.
        if dst.exists():
            return (f"'{dst.name}' already exists in {dst.parent.name}/ — nothing was "
                    f"copied. Rename or remove one of them first.")

        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

        # The undo for a copy is deleting the copy — never the original.
        _copy = dst.resolve()
        def _undo_copy():
            if not _copy.exists():
                return f"The copy '{_copy.name}' is already gone."
            if _copy.is_dir():
                shutil.rmtree(_copy)
            else:
                _copy.unlink()
            return f"Removed the copy in {_copy.parent.name}/."
        push_undo(f"copied {src.name} to {dst.parent.name}/", _undo_copy)

        return f"Copied: {src.name} → {dst.parent.name}/"

    except Exception as e:
        return f"Could not copy: {e}"


def rename_file(path: str, name: str = "", new_name: str = "") -> str:
    try:
        base     = _resolve_path(path)
        target   = (base / name) if name else base
        if not _is_safe_path(target):
            return _denial_message(target)
        if not target.exists():
            return f"Not found: {target.name}"
        if not new_name:
            return "No new name provided."

        new_path = target.parent / new_name
        if new_path.exists():
            return f"A file named '{new_name}' already exists here."

        old_path = target.resolve()
        target.rename(new_path)
        push_undo(f"renamed {old_path.name} to {new_name}",
                  _undo_move(old_path, new_path.resolve()))
        return f"Renamed: {target.name} → {new_name}"

    except Exception as e:
        return f"Could not rename: {e}"


def read_file(path: str, name: str = "", max_chars: int = 4000) -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _denial_message(target)
        if not target.exists():
            return f"File not found: {target.name}"
        if not target.is_file():
            return f"Not a file: {target.name}"

        content = target.read_text(encoding="utf-8", errors="ignore")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n[Truncated — {len(content)} total chars]"
        return content

    except Exception as e:
        return f"Could not read file: {e}"


def write_file(path: str, name: str = "", content: str = "",
               append: bool = False) -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _denial_message(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Snapshot before writing. None means "did not exist", which is a
        # different undo (delete it) from "existed and had this in it".
        previous: str | None = None
        undoable = True
        if target.exists():
            try:
                if target.stat().st_size > _UNDO_CONTENT_LIMIT:
                    undoable = False       # too large to hold in memory
                else:
                    previous = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                undoable = False           # binary, locked, unreadable

        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)

        action = "Appended to" if append else "Written to"
        if undoable:
            push_undo(f"wrote to {target.name}", _undo_write(target, previous))
            return f"{action}: {target.name}"
        return (f"{action}: {target.name}. "
                f"(Too large to keep a copy of the old contents, so this one "
                f"cannot be undone.)")
    except Exception as e:
        return f"Could not write file: {e}"


def find_files(name: str = "", extension: str = "",
               path: str = "home", max_results: int = 20) -> str:
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Search path not found: {path}"

        results    = []
        dir_count  = 0
        max_dirs   = 500  # performance + safety limit

        for item in search_path.rglob("*"):
            # A search may start in a safe folder and still walk into a key store.
            # _is_safe_path guards the starting point, not what lies below it, so the
            # refusal has to be repeated for every entry the walk reaches.
            if _is_sensitive(item):
                continue
            if item.is_dir():
                dir_count += 1
                if dir_count > max_dirs:
                    break
                continue
            if not item.is_file():
                continue
            if extension and item.suffix.lower() != extension.lower():
                continue
            if name and name.lower() not in item.name.lower():
                continue
            size = _format_size(item.stat().st_size)
            results.append(f"📄 {item.name} ({size}) — {item.parent}")
            if len(results) >= max_results:
                break

        if not results:
            query = name or extension or "files"
            return f"No {query} found in {search_path.name}/"

        return f"Found {len(results)} file(s):\n" + "\n".join(results)

    except Exception as e:
        return f"Search error: {e}"


def get_largest_files(path: str = "downloads", count: int = 10) -> str:
    count = min(count, 50)  # maksimum 50
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Path not found: {path}"

        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                try:
                    files.append((item.stat().st_size, item))
                except Exception:
                    continue

        files.sort(reverse=True)
        top = files[:count]

        if not top:
            return "No files found."

        lines = [f"Top {len(top)} largest files in {search_path.name}/:"]
        for size, f in top:
            lines.append(f"  {_format_size(size):>10}  {f.name}  ({f.parent})")

        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


def get_disk_usage(path: str = "home") -> str:
    try:
        target = _resolve_path(path)
        usage  = shutil.disk_usage(target)
        pct    = usage.used / usage.total * 100
        return (
            f"Disk usage ({target}):\n"
            f"  Total : {_format_size(usage.total)}\n"
            f"  Used  : {_format_size(usage.used)} ({pct:.1f}%)\n"
            f"  Free  : {_format_size(usage.free)}"
        )
    except Exception as e:
        return f"Could not get disk usage: {e}"


def organize_desktop() -> str:
    type_map = {
        "Images":    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"},
        "Documents": {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",
                      ".ppt", ".pptx", ".csv", ".odt", ".ods", ".odp"},
        "Videos":    {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
        "Music":     {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
        "Archives":  {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
        "Code":      {".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
                      ".cpp", ".java", ".cs", ".go", ".rs", ".sh"},
    }

    desktop = _get_desktop()
    moved, skipped = [], []
    journal: list[tuple[Path, Path]] = []   # (where it was, where it went)

    try:
        for item in desktop.iterdir():
            # Leave folders, hidden files and organize-folders untouched
            if item.is_dir() or item.name.startswith("."):
                continue
            if item.name in {k for k in type_map}:
                continue

            ext        = item.suffix.lower()
            target_dir = desktop / "Others"
            for folder, exts in type_map.items():
                if ext in exts:
                    target_dir = desktop / folder
                    break

            target_dir.mkdir(exist_ok=True)
            new_path = target_dir / item.name

            if new_path.exists():
                skipped.append(item.name)
                continue

            origin = item.resolve()
            shutil.move(str(item), str(new_path))
            journal.append((origin, new_path.resolve()))
            moved.append(f"{item.name} → {target_dir.name}/")

        # One command, dozens of moves — so one undo that reverses all of them.
        # Without this, "organize my desktop" is the single least reversible
        # thing the assistant can do to a person's files, and it was completely
        # ungated.
        if journal:
            def _undo_organize(entries=tuple(journal)):
                restored = 0
                for origin, moved_to in entries:
                    try:
                        if moved_to.exists():
                            origin.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(moved_to), str(origin))
                            restored += 1
                    except Exception as e:
                        print(f"[file] undo organize: {moved_to.name}: {e}")
                # Clear away the folders we created, but only while they are
                # empty — anything the user put in since stays.
                for folder in {m.parent for _o, m in entries}:
                    try:
                        if folder.exists() and folder.is_dir() and not any(folder.iterdir()):
                            folder.rmdir()
                    except Exception:
                        pass
                return f"{restored} file(s) put back on the desktop."
            push_undo(f"organized the desktop ({len(journal)} files)", _undo_organize)

        result = f"Desktop organized: {len(moved)} files moved."
        if moved:
            preview = moved[:8]
            result += "\n" + "\n".join(preview)
            if len(moved) > 8:
                result += f"\n... and {len(moved) - 8} more."
        if skipped:
            result += f"\n{len(skipped)} file(s) skipped (name conflict)."
        return result

    except Exception as e:
        return f"Could not organize desktop: {e}"


def get_file_info(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _denial_message(target)
        if not target.exists():
            return f"Not found: {target.name}"

        stat = target.stat()
        info = {
            "Name":      target.name,
            "Type":      "Folder" if target.is_dir() else "File",
            "Size":      _format_size(stat.st_size),
            "Location":  str(target.parent),
            "Created":   datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
            "Modified":  datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "Extension": target.suffix or "—",
        }
        return "\n".join(f"  {k}: {v}" for k, v in info.items())

    except Exception as e:
        return f"Could not get file info: {e}"

def file_controller(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = str(params.get("action") or "").lower().strip()
    path   = params.get("path", "desktop")
    name   = params.get("name", "")

    if player:
        print(f"[File] {action} {name or path}")  # terminal, not the HUD

    try:
        if action == "list":
            return list_files(path)

        elif action == "create_file":
            return create_file(path, name=name, content=params.get("content", ""))

        elif action == "create_folder":
            return create_folder(path, name=name)

        elif action == "delete":
            return delete_file(path, name=name)

        elif action == "move":
            return move_file(path, name=name, destination=params.get("destination", ""))

        elif action == "copy":
            return copy_file(path, name=name, destination=params.get("destination", ""))

        elif action == "rename":
            return rename_file(path, name=name, new_name=params.get("new_name", ""))

        elif action == "read":
            return read_file(path, name=name)

        elif action == "write":
            return write_file(
                path, name=name,
                content=params.get("content", ""),
                append=params.get("append", False)
            )

        elif action == "find":
            return find_files(
                name=name or params.get("name", ""),
                extension=params.get("extension", ""),
                path=path,
                max_results=min(int(params.get("max_results", 20)), 50),
            )

        elif action == "largest":
            return get_largest_files(
                path=path,
                count=int(params.get("count", 10)),
            )

        elif action == "disk_usage":
            return get_disk_usage(path)

        elif action == "organize_desktop":
            return organize_desktop()

        elif action == "info":
            return get_file_info(path, name=name)

        else:
            return f"Unknown action: '{action}'"

    except Exception as e:
        return f"File controller error ({action}): {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "file_controller",
    "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, "
        "find, disk usage. "
        "Use when the user asks to list, find, read, write, move, copy, rename or "
        "delete a file or folder, or asks how much space is left.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"
            },
            "append": {
                # Without this the model could not ask to append, and the write
                # path defaults to overwrite — so "add this line to my notes"
                # replaced the file. The parameter existed; the model could not
                # say it.
                "type": "BOOLEAN",
                "description": "For action='write': add to the end instead of replacing the file"
            },
            "max_results": {
                "type": "INTEGER",
                "description": "For action='find': how many matches to return (max 50)"
            },
            "path": {
                "type": "STRING",
                "description": "File/folder path or shortcut: desktop, downloads, documents, home"
            },
            "destination": {
                "type": "STRING",
                "description": "Destination path for move/copy"
            },
            "new_name": {
                "type": "STRING",
                "description": "New name for rename"
            },
            "content": {
                "type": "STRING",
                "description": "Content for create_file/write"
            },
            "name": {
                "type": "STRING",
                "description": "File name to search for"
            },
            "extension": {
                "type": "STRING",
                "description": "File extension to search (e.g. .pdf)"
            },
            "count": {
                "type": "INTEGER",
                "description": "Number of results for largest"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": file_controller,
}
