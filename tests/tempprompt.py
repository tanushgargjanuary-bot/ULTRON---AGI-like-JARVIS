"""A throwaway system prompt and a banner the test can press, shared by the prompt tests.

`tests/test_prompt_editor.py` and `tests/test_prompt_gate.py` need the same fixture: a
copy of `core/prompt.txt` in a temporary folder, so a test that applies a change never
edits the real prompt, and the interface the tool talks to — a banner with a CONFIRM
button — standing where `ui.py` stands. Written once, because the second copy of a
fixture is how a suite drifts.

Importable both ways on purpose, like `tempconfig`: `scripts/verify.py` discovers tests
with the tests folder on the path, so the module is `tempprompt`; `python -m unittest
tests.x` imports it as `tests.tempprompt`.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions import prompt_editor  # noqa: E402
from core import confirm as hud  # noqa: E402
from core import failures, prompt_store  # noqa: E402


def press_the_button(log: list[str], accepted: bool = True) -> str:
    """Press CONFIRM (or CANCEL) on the banner that is up, wait for the work, return what the HUD said.

    Shared by the prompt tests and the self-change tests: the second copy of a fixture is how a suite
    drifts, and the debt scanner counts a repeated body.
    """
    seen = len(log)
    hud.resolve(accepted)
    for thread in threading.enumerate():
        if thread.name.startswith("confirm-"):
            thread.join(timeout=5)
    return " ".join(log[seen:])


class WithATemporaryPrompt(unittest.TestCase):
    """Every test gets its own prompt file, its own history folder and its own banner."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.prompt = self.folder / "prompt.txt"
        shutil.copyfile(ROOT / "core" / "prompt.txt", self.prompt)
        self._real_prompt = prompt_store.PROMPT_PATH
        prompt_store.PROMPT_PATH = self.prompt
        prompt_store.set_store(self.folder / "versions")
        failures.clear()
        self.original = prompt_store.read()
        # The interface: a banner the test can press, standing where ui.py stands.
        self.banners: list[tuple[str, str]] = []
        self.hud_log: list[str] = []
        hud.bind(show=lambda title, detail: self.banners.append((title, detail)),
                 hide=lambda: None, log=self.hud_log.append)

    def tearDown(self):
        prompt_store.PROMPT_PATH = self._real_prompt
        prompt_store.set_store(None)
        hud._show_cb = hud._hide_cb = hud._log_cb = None
        hud._pending = None
        shutil.rmtree(self.folder, ignore_errors=True)

    def call(self, **parameters) -> str:
        return prompt_editor.system_prompt(parameters)

    # A passage that is in the shipped prompt, and the change the test wants to see
    # applied. The first version of this test used "Be concise.", which the prompt
    # does not contain — the stage was refused, correctly, and eleven tests failed
    # because of a fixture rather than a fault.
    FIND = "Brevity is the default."
    REPLACE = "Brevity is the default, and one line is usually enough."
    OTHER_FIND = "[MANNER]"                  # appears once in core/prompt.txt
    OTHER_REPLACE = "[MANNER AND TONE]"

    def stage_small_change(self, reason="be shorter"):
        return self.call(action="stage", reason=reason,
                         find=self.FIND, replace=self.REPLACE)

    def stage(self, find=None, replace=None, reason="be shorter") -> str:
        """Stage a change and return its id."""
        self.call(action="stage", reason=reason, find=find or self.FIND,
                  replace=replace or self.REPLACE)
        return prompt_store.pending()[-1].id

    def click(self, accepted: bool = True) -> str:
        """Press CONFIRM (or CANCEL) on the banner that is up, and wait for the work."""
        return press_the_button(self.hud_log, accepted)

    def confirm_by_voice_and_click(self, proposal: str) -> str:
        """The owner's way: say yes, then press the button. Returns what the HUD said."""
        self.call(action="confirm", proposal=proposal)
        return self.click()

    def unchanged(self) -> bool:
        return prompt_store.read() == self.original
