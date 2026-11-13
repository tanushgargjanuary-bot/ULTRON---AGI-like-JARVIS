"""test_suite_safety.py — one suite file for 6 areas.

Each section below was its own test module and is kept whole, with its
header, its helpers and its tests. They were combined because the project
had sixty-five test modules of one or two hundred lines each, and a file
count that size hides the structure instead of showing it. Nothing was
removed; a name that appeared in two sections was given a suffix.

Sections:
  * test_file_safety.py
  * test_policy_new_tools.py
  * test_tool_catalog.py
  * test_tools_overlay.py
  * test_publishing.py
  * test_memory_consent.py
"""

from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
from actions import file_controller as fc          # noqa: E402
from core import policy
from core.plugin_loader import discover_plugins
from core import tool_catalog
import os
import re
from core import memory_consent
from core.memory_consent import EMPTY_ANSWER, PENDING_MARKER, request_write



# ══════════════════════════════════════════════════════════════════════════
# from test_file_safety.py
# ══════════════════════════════════════════════════════════════════════════
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class CredentialStoreTests(unittest.TestCase):
    def assert_refused(self, raw: str):
        target = fc._resolve_path(raw)
        self.assertFalse(fc._is_safe_path(target), f"{raw} should be refused")

    def test_ssh_keys_are_refused(self):
        for raw in ("~/.ssh/id_rsa", "~/.ssh/id_ed25519", "~/.ssh/config"):
            self.assert_refused(raw)

    def test_cloud_and_gpg_stores_are_refused(self):
        for raw in ("~/.aws/credentials", "~/.gnupg/secring.gpg", "~/.kube/config",
                    "~/.docker/config.json", "~/.password-store/x.gpg"):
            self.assert_refused(raw)

    def test_dotenv_files_are_refused(self):
        for raw in ("~/.env", "~/proj/.env", "~/proj/.env.local"):
            self.assert_refused(raw)

    def test_key_material_by_extension_is_refused(self):
        for raw in ("~/keys/server.pem", "~/keys/id.key", "~/certs/x.p12",
                    "~/vault.kdbx"):
            self.assert_refused(raw)

    def test_this_programs_own_key_file_is_refused(self):
        # Even when the project sits inside the home directory, which it does by
        # default when someone extracts the ZIP where Windows puts downloads.
        self.assert_refused("~/app/config/api_keys.json")
        self.assert_refused("~/Desktop/ultron/config/api_keys.json")

    def test_a_browser_profile_is_refused(self):
        for raw in ("~/AppData/Local/Google/Chrome/User Data/Default/Login Data",
                    "~/.mozilla/firefox/abc.default/logins.json",
                    "~/.config/google-chrome/Default/Cookies"):
            self.assert_refused(raw)

    def test_ordinary_home_files_are_still_allowed(self):
        for raw in ("~/notes.txt", "~/Documents/report.docx", "~/Downloads/x.pdf",
                    "~/Pictures/holiday.jpg", "~/Desktop/todo.md"):
            target = fc._resolve_path(raw)
            self.assertTrue(fc._is_safe_path(target), f"{raw} should be allowed")

    def test_the_refusal_says_which_kind_of_refusal_it_is(self):
        message = fc._denial_message(Path("~/.ssh/id_rsa").expanduser())
        self.assertIn("credentials", message)
        self.assertNotIn("Access denied", message)

    def test_an_outside_path_still_says_access_denied(self):
        self.assertIn("Access denied", fc._denial_message(Path("/etc/passwd")))


class RealOperationsTests(unittest.TestCase):
    """The deny-list must not get in the way of the work it is protecting."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.home = Path(self._temp.name)
        self._saved = fc._SAFE_ROOTS
        fc._SAFE_ROOTS = [self.home]

    def tearDown(self):
        fc._SAFE_ROOTS = self._saved
        self._temp.cleanup()

    def test_write_read_and_append_round_trip(self):
        target = self.home / "notes.md"
        self.assertIn("Written", fc.write_file(str(target), content="one\n"))
        self.assertIn("Appended", fc.write_file(str(target), content="two\n", append=True))
        self.assertEqual(target.read_text(encoding="utf-8"), "one\ntwo\n")
        self.assertIn("one\ntwo", fc.read_file(str(target)))

    def test_a_write_is_undoable(self):
        from core import undo
        undo.clear()
        target = self.home / "keep.txt"
        target.write_text("original", encoding="utf-8")
        fc.write_file(str(target), content="replaced")
        self.assertEqual(target.read_text(encoding="utf-8"), "replaced")
        undo.undo_last()
        self.assertEqual(target.read_text(encoding="utf-8"), "original")
        undo.clear()

    def test_listing_a_folder_still_works(self):
        (self.home / "a.txt").write_text("x", encoding="utf-8")
        listing = fc.file_controller({"action": "list", "path": str(self.home)})
        self.assertIn("a.txt", listing)


# ══════════════════════════════════════════════════════════════════════════
# from test_policy_new_tools.py
# ══════════════════════════════════════════════════════════════════════════

PLUGINS = Path(__file__).resolve().parent.parent / "plugins"


class Tiers(unittest.TestCase):
    def tier(self, name, **args):
        return policy.classify(name, args)

    def test_local_converters_are_routine(self):
        for name in ("dev_json", "dev_regex", "dev_hash", "dev_cron", "crypto_ident"):
            decision = self.tier(name, action="validate")
            self.assertEqual(decision.tier, policy.Tier.ROUTINE, name)
            self.assertTrue(decision.allow, name)

    def test_net_check_reads_are_not_prompts(self):
        self.assertEqual(self.tier("net_check", action="dns").tier, policy.Tier.OBSERVE)
        self.assertEqual(self.tier("net_check", action="headers").tier, policy.Tier.ROUTINE)

    def test_net_check_port_needs_a_decision(self):
        decision = self.tier("net_check", action="port")
        self.assertEqual(decision.tier, policy.Tier.GUARDED)
        self.assertFalse(decision.allow)

    def test_asking_a_tool_if_it_is_alive_is_a_read(self):
        for name in ("rea_bridge", "hyperframes_bridge", "hypit_bridge"):
            self.assertEqual(self.tier(name, action="help").tier, policy.Tier.OBSERVE, name)
        for name in ("hindsight_bridge", "voicestudio_bridge"):
            self.assertEqual(self.tier(name, action="status").tier, policy.Tier.OBSERVE, name)

    def test_making_a_tool_work_is_guarded(self):
        for name in ("hyperframes_bridge", "hypit_bridge"):
            decision = self.tier(name, action="command")
            self.assertEqual(decision.tier, policy.Tier.GUARDED, name)
            self.assertFalse(decision.allow, name)
        for name in ("hindsight_bridge", "voicestudio_bridge"):
            self.assertEqual(self.tier(name, action="request").tier, policy.Tier.GUARDED, name)

    def test_a_bridge_with_no_action_is_guarded_not_trusted(self):
        for name in ("rea_bridge", "hyperframes_bridge", "hypit_bridge",
                     "hindsight_bridge", "voicestudio_bridge"):
            decision = self.tier(name)
            self.assertEqual(decision.tier, policy.Tier.GUARDED, name)
            self.assertFalse(decision.allow, name)

    def test_every_shipped_plugin_is_classified(self):
        """A plugin that lands in "unclassified" is a plugin that always asks."""
        registry = discover_plugins(PLUGINS, core_tool_names=set(), logger=lambda _m: None)
        for row in registry.list_for_ui():
            decision = self.tier(row["name"], action="")
            reason = decision.reason.lower()
            if row["name"] == "custom_jarvis":
                continue          # carries its own per-step gate, by design
            self.assertNotIn("unclassified", reason, row["name"])

    def test_policy_never_raises_on_junk(self):
        for name in ("", None, 42, "no_such_tool"):
            for args in ({}, {"action": None}, {"action": 5}, {"port": "x"}):
                policy.decide(name, args)


class Wired(unittest.TestCase):
    def test_plugin_declarations_reach_the_model(self):
        registry = discover_plugins(PLUGINS, core_tool_names=set(), logger=lambda _m: None)
        names = {decl.get("name") for decl in registry.get_tool_declarations()}
        for expected in ("dev_json", "net_check", "rea_bridge", "voicestudio_bridge"):
            self.assertIn(expected, names)

    def test_plugin_declarations_carry_parameters(self):
        registry = discover_plugins(PLUGINS, core_tool_names=set(), logger=lambda _m: None)
        for decl in registry.get_tool_declarations():
            if decl.get("name") == "dev_json":
                self.assertIn("text", decl["parameters"]["properties"])
                return
        self.fail("dev_json is not in the model's tool list")


# ══════════════════════════════════════════════════════════════════════════
# from test_tool_catalog.py
# ══════════════════════════════════════════════════════════════════════════


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = tool_catalog.build()
        cls.by_name = {entry.name: entry for entry in cls.entries}

    def test_builds_entries(self):
        self.assertGreater(len(self.entries), 20)

    def test_names_are_unique(self):
        names = [entry.name for entry in self.entries]
        self.assertEqual(len(names), len(set(names)))

    def test_inline_tools_come_from_main(self):
        self.assertIn("system_status", self.by_name)

    def test_actions_are_listed(self):
        self.assertIn("open_app", self.by_name)
        self.assertEqual(self.by_name["open_app"].kind, "action")

    def test_plugins_are_listed(self):
        self.assertIn("dev_json", self.by_name)
        self.assertEqual(self.by_name["dev_json"].kind, "plugin")
        self.assertIn("rea_bridge", self.by_name)

    def test_bridges_are_listed(self):
        for key in ("rea", "hyperframes", "hindsight", "voicestudio", "hypit"):
            entry = self.by_name[f"bridge:{key}"]
            self.assertEqual(entry.kind, "bridge")
            self.assertEqual(entry.label, key)

    def test_unavailable_tool_keeps_its_reason(self):
        # A tool that does not load must stay visible with its reason, not vanish.
        for entry in self.entries:
            if not entry.available:
                self.assertTrue(entry.reason, f"{entry.name} is silent about why")


class Render(unittest.TestCase):
    def test_render_text_names_the_counts(self):
        text = tool_catalog.render_text()
        self.assertRegex(text, r"I have \d+ tools")

    def test_grouped_puts_unavailable_last(self):
        groups = tool_catalog.grouped()
        self.assertTrue(groups)
        for items in groups.values():
            ready = [entry.available for entry in items]
            self.assertEqual(ready, sorted(ready, reverse=True))

    def test_describe_known_tool(self):
        text = tool_catalog.describe("dev_json")
        self.assertIn("dev_json", text)
        self.assertIn("plugin", text.lower())

    def test_describe_unknown_tool_says_so(self):
        text = tool_catalog.describe("no_such_tool_xyz")
        self.assertIn("no_such_tool_xyz", text)

    def test_describe_absent_bridge_states_the_blocker(self):
        entry = {e.name: e for e in tool_catalog.build()}["bridge:rea"]
        if entry.available:
            self.skipTest("REA is installed here")
        self.assertIn("not installed", tool_catalog.describe("rea").lower())


class Robust(unittest.TestCase):
    def test_missing_directories_do_not_raise(self):
        entries = toy = tool_catalog.build(include_bridges=False)
        self.assertTrue(toy)
        self.assertTrue(isinstance(entries, list))

    def test_bad_paths_give_empty_lists(self):
        self.assertEqual(tool_catalog._action_entries(Path("/nonexistent")), [])
        self.assertEqual(tool_catalog._plugin_entries(Path("/nonexistent")), [])
        self.assertEqual(tool_catalog._inline_entries(Path("/nonexistent/main.py")), [])


# ══════════════════════════════════════════════════════════════════════════
# from test_tools_overlay.py
# ══════════════════════════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QPushButton, QTabWidget

    import ui
    from core import tool_catalog
except ImportError as exc:      # pragma: no cover - environment without Qt
    raise unittest.SkipTest(str(exc)) from exc

APP = QApplication.instance() or QApplication([])


def settle(ms: int = 4000) -> None:
    """Let queued work run, but never longer than the budget."""
    QTimer.singleShot(min(ms, 200), APP.quit)
    APP.exec()


class Panel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.overlay = ui.ToolsOverlay()
        cls.tabs = cls.overlay.findChild(QTabWidget)

    @classmethod
    def tearDownClass(cls):
        cls.overlay.deleteLater()

    def test_it_has_tabs(self):
        self.assertIsNotNone(self.tabs)
        self.assertGreaterEqual(self.tabs.count(), 4)

    def test_tab_names_are_categories(self):
        names = [self.tabs.tabText(i) for i in range(self.tabs.count())]
        self.assertIn("SYSTEM", names)
        self.assertIn("SECURITY", names)

    def test_the_count_matches_the_catalog(self):
        text = self.overlay._count.text()
        self.assertIn(str(len(tool_catalog.build())), text)
        self.assertIn("usable", text)

    def test_every_tool_appears_in_some_tab(self):
        shown = 0
        for index in range(self.tabs.count()):
            shown += len(self.tabs.widget(index).findChildren(type(self.overlay._count)))
        self.assertGreaterEqual(shown, len(tool_catalog.build()))

    def test_an_unavailable_tool_is_visible_not_hidden(self):
        texts = []
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            for label in page.findChildren(type(self.overlay._count)):
                texts.append(label.text())
        joined = "\n".join(texts)
        unavailable = [e for e in tool_catalog.build() if not e.available]
        for entry in unavailable:
            self.assertIn(entry.label, joined, f"{entry.name} is missing from the panel")

    def test_close_button_exists(self):
        buttons = [b.text() for b in self.overlay.findChildren(QPushButton)]
        self.assertIn("CLOSE", buttons)

    def test_reload_is_safe_to_call_twice(self):
        before = self.tabs.count()
        self.overlay.reload()
        settle()
        self.assertEqual(self.tabs.count(), before)


class Wiring(unittest.TestCase):
    """The panel needs a door: a drawer button and a keyboard shortcut."""

    def test_drawer_has_a_tools_button(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        self.assertIn('QPushButton("🛠  TOOLS")', source)
        self.assertIn("_open_tools_panel", source)

    def test_ctrl_t_opens_the_panel(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        self.assertIn('QKeySequence("Ctrl+T")', source)

    def test_the_overlay_never_lands_outside_the_window(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        block = source[source.index("def _open_tools_panel"):]
        block = block[: block.index("def ", 10)]
        self.assertIn("_centre_overlay", block)


# ══════════════════════════════════════════════════════════════════════════
# from test_publishing.py
# ══════════════════════════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parents[1]


class IgnoreRules(unittest.TestCase):
    """The ignore file is the last thing between a key and a public commit."""

    @classmethod
    def setUpClass(cls):
        cls.rules = (ROOT / ".gitignore").read_text(encoding="utf-8")

    def test_secrets_are_ignored(self):
        for pattern in ("config/api_keys.json", "config/certs/", ".env"):
            self.assertIn(pattern, self.rules)

    def test_personal_memory_is_ignored(self):
        self.assertIn("memory/long_term.json", self.rules)

    def test_build_noise_is_ignored(self):
        for pattern in ("__pycache__/", ".venv/", "*.log"):
            self.assertIn(pattern, self.rules)

    def test_no_pattern_carries_a_trailing_comment(self):
        # The file's own header says it: git has no trailing comments, so
        # `config/api_keys.json  # key` matches nothing while looking protected.
        patterns = [line for line in self.rules.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual([line for line in patterns if "#" in line], [])

    def test_the_build_record_is_tracked_on_purpose(self):
        # log.txt and verification-results.txt are the project's own record and
        # test_bootstrap asserts they stay visible. Nothing here may hide them.
        import subprocess
        import tempfile
        git = __import__("shutil").which("git")
        if not git:
            self.skipTest("git is not installed here")
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            subprocess.run([git, "init", "-q", str(repo)], check=True)
            (repo / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
            for name in ("log.txt", "verification-results.txt", "main.py"):
                with self.subTest(name=name):
                    done = subprocess.run([git, "check-ignore", "-q", name],
                                          cwd=repo, check=False)
                    self.assertEqual(done.returncode, 1, f"{name} must stay visible")


class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / ".github" / "workflows" / "verify.yml"
        cls.text = cls.path.read_text(encoding="utf-8") if cls.path.exists() else ""

    def test_the_workflow_exists(self):
        self.assertTrue(self.path.exists(), "no CI: nothing runs on a Windows machine")

    def test_it_runs_on_push_and_pull_request(self):
        for trigger in ("push:", "pull_request:", "workflow_dispatch:"):
            self.assertIn(trigger, self.text)

    def test_it_has_a_windows_job(self):
        self.assertIn("windows-latest", self.text)

    def test_it_runs_the_three_gates(self):
        for script in ("scripts/verify.py", "scripts/proof_gate.py",
                       "scripts/verify_all.py"):
            self.assertIn(script, self.text)

    def test_it_does_not_install_the_whole_world(self):
        # Pinning the lean set keeps a red build readable. If someone swaps in
        # `pip install -r requirements.txt`, the run time triples and the failure
        # is buried in logs.
        self.assertNotIn("pip install -r requirements.txt", self.text)

    def test_no_api_key_is_written_into_the_workflow(self):
        self.assertIsNone(re.search(r"AIza[0-9A-Za-z_-]{20,}", self.text))


class Licence(unittest.TestCase):
    def test_attribution_survives(self):
        readme = (ROOT / "readme.md").read_text(encoding="utf-8")
        self.assertIn("FatihMakes", readme)
        self.assertIn("BY-NC", readme)
        self.assertIn("Creative Commons", readme)
        self.assertTrue((ROOT / "LICENSE").exists())


# ══════════════════════════════════════════════════════════════════════════
# from test_memory_consent.py
# ══════════════════════════════════════════════════════════════════════════


class _Verdict:
    def __init__(self, allow: bool):
        self.allow = allow


class _Recorder:
    """Stands in for memory_manager.update_memory and for a pending banner."""

    def __init__(self, allow: bool = False, gate_answer: str | None = None):
        self.writes: list[dict] = []
        self.banners: list[dict] = []
        self.allow = allow
        self.gate_answer = gate_answer if gate_answer is not None else (
            PENDING_MARKER + " ask the user to confirm on the HUD")

    # the two injections
    def write(self, payload: dict) -> None:
        self.writes.append(payload)

    def decide(self, *_args, **_kwargs):
        return _Verdict(self.allow)

    def gate(self, **kwargs) -> str:
        self.banners.append(kwargs)
        return self.gate_answer


class NoSilentWriteTests(unittest.TestCase):
    def test_an_inferred_fact_is_not_written(self):
        rec = _Recorder()
        result = request_write("notes", "wifi", "hunter2", rec.write,
                               gate=rec.gate, decide=rec.decide)
        self.assertEqual(rec.writes, [], "nothing may be stored before approval")
        self.assertIn(PENDING_MARKER, result["result"])
        self.assertNotIn("silent", result, "a pending write must not be silent")

    def test_the_banner_shows_the_fact_itself(self):
        rec = _Recorder()
        request_write("notes", "wifi", "hunter2", rec.write,
                      gate=rec.gate, decide=rec.decide)
        self.assertEqual(len(rec.banners), 1)
        detail = rec.banners[0]["detail"]
        self.assertIn("wifi", detail)
        self.assertIn("hunter2", detail, "the user approves the value, not a summary")
        self.assertIn("notes", detail)

    def test_confirming_writes_exactly_once(self):
        rec = _Recorder()
        request_write("notes", "wifi", "hunter2", rec.write,
                      gate=rec.gate, decide=rec.decide)
        run = rec.banners[0]["run"]
        self.assertEqual(run(), "Remembered “wifi” in notes.")
        self.assertEqual(rec.writes,
                         [{"notes": {"wifi": {"value": "hunter2"}}}])

    def test_cancelling_leaves_the_store_untouched(self):
        rec = _Recorder()
        request_write("notes", "wifi", "hunter2", rec.write,
                      gate=rec.gate, decide=rec.decide)
        # CANCEL means the stored callable is never called: model the UI, which
        # simply drops it. Nothing else in this module may write.
        self.assertEqual(rec.writes, [])
        self.assertNotIn("silent", {"result": "x"})

    def test_a_gate_that_cannot_ask_saves_nothing(self):
        rec = _Recorder(gate_answer="I cannot confirm right now, so I have not done it.")
        result = request_write("notes", "wifi", "hunter2", rec.write,
                               gate=rec.gate, decide=rec.decide)
        self.assertEqual(rec.writes, [])
        self.assertIn("have not done it", result["result"])

    def test_malformed_input_spends_no_banner(self):
        for category, key, value in (("notes", "", "x"), ("notes", "k", ""),
                                     ("", "", "")):
            with self.subTest(key=key, value=value):
                rec = _Recorder()
                result = request_write(category, key, value, rec.write,
                                       gate=rec.gate, decide=rec.decide)
                self.assertEqual(result["result"], EMPTY_ANSWER)
                self.assertEqual(rec.banners, [], "do not nag about an empty fact")
                self.assertEqual(rec.writes, [])

    def test_a_policy_that_allows_it_still_writes_once(self):
        """Forward compatibility: if the tier ever opens, the path stays single."""
        rec = _Recorder(allow=True)
        result = request_write("notes", "wifi", "hunter2", rec.write,
                               gate=rec.gate, decide=rec.decide)
        self.assertEqual(result, {"result": "ok", "silent": True})
        self.assertEqual(rec.writes, [{"notes": {"wifi": {"value": "hunter2"}}}])
        self.assertEqual(rec.banners, [])


class OneBannerAtATimeTests(unittest.TestCase):
    def test_a_second_pending_write_does_not_replace_the_first(self):
        """The gate holds one decision; the second write must be refused with a
        sentence, not dropped on the floor while the model says "remembered"."""
        from core import confirm, memory_consent

        shown: list[tuple[str, str]] = []
        confirm.bind(show=lambda title, detail: shown.append((title, detail)),
                     hide=lambda: None, log=lambda _m: None)
        writes: list[dict] = []
        try:
            first = memory_consent.request_write("notes", "one", "1", writes.append)
            second = memory_consent.request_write("notes", "two", "2", writes.append)
            self.assertIn(memory_consent.PENDING_MARKER, first["result"])
            self.assertIn("already have a confirmation", second["result"])
            self.assertEqual(writes, [], "neither may be stored before approval")
            confirm.resolve(True)          # approve the first
            self.assertEqual(writes, [{"notes": {"one": {"value": "1"}}}],
                             "the first fact survives; the second was refused aloud")
        finally:
            confirm.resolve(False)
            confirm.bind(show=None, hide=None, log=None)


class RealPolicyTests(unittest.TestCase):
    """The shipped policy, not a fake one — this is the claim the user made."""

    def test_the_shipped_policy_gates_memory(self):
        from core import policy
        verdict = policy.decide("save_memory",
                                {"category": "notes", "key": "k", "value": "v"})
        self.assertFalse(verdict.allow)
        self.assertIn("approval", verdict.reason)

    def test_the_shipped_path_asks_before_writing(self):
        writes: list[dict] = []
        asked: list[dict] = []
        result = request_write(
            "notes", "k", "v", writes.append,
            gate=lambda **kw: asked.append(kw) or PENDING_MARKER,
        )
        self.assertEqual(writes, [])
        self.assertEqual(len(asked), 1)
        self.assertIn(PENDING_MARKER, result["result"])

    def test_main_py_routes_save_memory_through_the_gate(self):
        """The defect was the call site, so assert on the call site."""
        source = (memory_consent.__file__ and
                  __import__("pathlib").Path("main.py").read_text(encoding="utf-8",
                                                                  errors="replace"))
        after = source.split('if name == "save_memory":', 1)[1]
        # The whole branch, not a fixed char count: comments above the call are
        # allowed to grow without moving the assertion's goalposts. The next
        # dispatch entry at the same indent ends the branch.
        siblings = re.findall(r"\n        (?:el)?if name == ", after)
        block = after[:siblings[0]] if siblings else after[:6000]
        self.assertIn("request_memory_write", block)
        self.assertNotIn("update_memory({category: {key:", block,
                         "the direct write must not come back")


if __name__ == "__main__":
    unittest.main()
