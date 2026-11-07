# Installing Ultron

Three ways, from easiest to most involved. Most people want the first one.

---

## Starting it, all the ways it starts

Three entry points, and only one of them needs care.

| How | Works? | What it does |
|---|---|---|
| Double-click **`run.bat`** | Yes, always | Finds a supported Python, builds `.venv` if needed, installs what is missing, starts the app. |
| **`.venv\Scripts\python.exe main.py`** | Yes | The same Python `run.bat` uses, without the checks. Fastest once the folder is set up. |
| **`python main.py`** with the system Python | Only if that Python is 3.11–3.13 **and** has the packages | Usually neither. It now says so in two sentences instead of a traceback. |

`run.bat` is the answer to "it will not start". It repairs its own environment: a `.venv`
built by a Python that has since been removed is moved aside and rebuilt.

The same rule applies to the repository's own scripts. Run them on the folder's Python:

```powershell
.venv\Scripts\python.exe scripts\local_model.py check
```

---

## 1. The installer (one file)

1. Run **`UltronSetup-1.2.27.exe`**.
2. Click **Next** three times. Do **not** expect a password prompt: Ultron installs
   into your own folder, not into `Program Files`, so Windows never asks.
3. It opens **by itself** at the end. The first screen asks for a provider and a key.

You get an **Ultron** shortcut in the Start menu, and one on the desktop if you left
the box ticked.

**One thing must be on the PC already: Python 3.11, 3.12 or 3.13.** The installer
checks for it and says so in a sentence if it is missing. Get it from
[python.org](https://www.python.org/downloads/) and **tick "Add python.exe to PATH"**
during setup. Ultron builds its own private environment from there, so nothing else
on your PC is touched.

### Removing it

Windows **Settings → Apps → Ultron → Uninstall** (or the Start-menu entry).

The program and its Python environment are removed. **Your API keys, your memory and
your logs are kept**, and the uninstaller tells you where they are:

```
%LOCALAPPDATA%\Programs\Ultron\config\api_keys.json
%LOCALAPPDATA%\Programs\Ultron\memory\
```

Delete that folder yourself if you want them gone too. The uninstaller does not, on
purpose: uninstalling a program should not quietly throw away somebody's key.

---

## 2. From the folder, without an installer

If you already have the folder (a ZIP, or a clone):

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

The first run builds `.venv`, installs `requirements.txt`, and opens the setup
screen. Nothing outside the folder is modified.

If Windows blocks the script because it came from a download:

```powershell
Unblock-File .\run.ps1
```

---

## 3. A build with no Python on the machine

For handing Ultron to someone who will not install Python. This must be built **on
Windows**:

```powershell
python -m pip install pyinstaller
python -m PyInstaller packaging\ultron.spec --noconfirm
```

That writes `dist\Ultron\` — a folder with an interpreter inside it. The result is a
few hundred megabytes, most of it Qt.

**Status: written and reviewed, not yet built on Windows.** The file list it uses is
checked against the tree by `tests/test_installer.py`, so it cannot point at
something that has been renamed. But "it works" needs a build on a Windows PC, and
that has not happened yet. The installer above is the path with real testing behind
it.

---

## Building the installer yourself

You need **Inno Setup 6** — free, separate from Python:
<https://jrsoftware.org/isdl.php>

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1
```

It reads the version from `packaging\version.txt`, copies exactly the files listed in
`packaging\payload.txt` into `build\stage`, and writes
`build\installer\UltronSetup-<version>.exe`.

Useful options:

```powershell
# A different Inno Setup install
.\packaging\build_installer.ps1 -InnoSetup 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'

# Reuse the files already staged (the .iss file is what you are editing)
.\packaging\build_installer.ps1 -SkipStage
```

### What goes in, and what does not

`packaging\payload.txt` is the one list. It names the folders and files that ship.
It deliberately leaves out `.git`, `.venv`, build output, and **your own
configuration** — a fresh install must start at the setup screen, not with somebody
else's keys.

A test checks that every path in that list exists before a build can be called
honest, and the build script stops if it finds `.git` or `.venv` in the staged
folder.

---

## If something goes wrong

| What you see | What it means |
|---|---|
| "Ultron needs Python 3.11, 3.12 or 3.13" | Install Python from python.org and tick "Add python.exe to PATH". |
| A blue "Windows protected your PC" box | Click **More info → Run anyway**. The installer is not code-signed; signing costs money every year and needs a company name. |
| The window opens and closes | Run `run.ps1` in PowerShell instead. It keeps the window open and prints the reason. |
| "could not load the Qt platform plugin" | A missing graphics driver. Update the graphics driver, then try again. |

Logs live next to the app, in the folder it installed to. **Never share a log that
contains API keys** — the app redacts them, but read before you paste.
