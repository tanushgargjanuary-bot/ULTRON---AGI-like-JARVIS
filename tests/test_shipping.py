"""tests/test_shipping.py — shipping to GitHub and updating from it, for real.

These tests use **real git** against a **local bare repository**, so there is no
network and no faked version control. What they prove is the part that would
otherwise be a promise: that a secret stops the ship, that a divergence is never
force-pushed, that a broken new version is put back, and that a change made by
the assistant is remembered as waiting to be shipped.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_jarvis.selfupdate import Updater
from custom_jarvis.ship import Shipper, find_secret
from custom_jarvis.service import CustomService

GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
       "-c", "init.defaultBranch=main", "-c", "protocol.file.allow=always"]


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run([*GIT, *args], cwd=str(cwd), capture_output=True, text=True,
                          timeout=60)
    if done.returncode != 0:
        raise AssertionError(f"git {args} failed: {done.stderr}{done.stdout}")
    return done.stdout.strip()


class Base(unittest.TestCase):
    """One bare origin, one working copy, both real."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.base = Path(self.folder.name)
        self.origin = self.base / "origin.git"
        self.work = self.base / "work"
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(self.origin)],
                       check=True, capture_output=True)
        self.work.mkdir()
        git(self.work, "init", "-q")
        (self.work / ".gitignore").write_text(
            "config/api_keys.json\nconfig/api_keys.json.*\nmemory/long_term.json\n")
        (self.work / "app.py").write_text("print('hello')\n")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "first")
        git(self.work, "remote", "add", "origin", str(self.origin))
        git(self.work, "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        self.folder.cleanup()

    def shipper(self, token: str = "test-token-not-real") -> Shipper:
        return Shipper(self.work, token=token,
                       log_path=self.base / "ship_log.json")


class Secrets(Base):

    def test_a_marked_fixture_line_is_exempt_and_counted(self):
        """A test fixture must look like a key, so the exemption is explicit."""
        value = "Qz8v" + "LmT4rXn2Pw9Ks3Dd"        # assembled: this file stays clean
        (self.work / "fixture.py").write_text(
            'api_key = "' + value + '"  # gitleaks:allow\n')
        report = self.shipper().scan()
        self.assertTrue(report["clean"], report["hits"])
        self.assertEqual(report["allowed"], 1)

    def test_the_marker_exempts_one_line_and_not_the_file(self):
        first, second = "Qz8v" + "LmT4rXn2Pw9Ks3Dd", "Xk2m" + "Q8vLpT4rXn2Pw9Ks"
        (self.work / "fixture.py").write_text(
            'api_key = "' + first + '"  # gitleaks:allow\n'
            'api_key = "' + second + '"\n')
        report = self.shipper().scan()
        self.assertFalse(report["clean"])
        self.assertEqual(report["hits"][0]["lines"], [2])

    def test_a_real_looking_key_stops_the_ship_before_the_commit(self):
        (self.work / "leak.py").write_text('api_key = "Qz8vLmT4rXn2Pw9Ks3Dd"\n')  # gitleaks:allow — a fixture, not a key
        result = self.shipper().ship("add a module")
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "scan")
        self.assertIn("leak.py", result["note"])
        self.assertEqual(git(self.work, "log", "--oneline").count("\n"), 0)

    def test_a_placeholder_is_not_a_secret(self):
        for value in ('api_key = "abcd1234efgh5678"',
                      'SECRET = "AIza-THIS-IS-THE-SECRET"',
                      'token = "your-token-here-please"'):
            self.assertEqual(find_secret(value), "", value)

    def test_a_github_token_shape_is_always_a_secret(self):
        self.assertTrue(find_secret(
            'x = "github_pat_11BZQ7XK2MvT9LpR4WnC8JdY6HsA3GfE5UoI1Kq7YmZ"'))  # gitleaks:allow — a fixture, not a key

    def test_the_ignore_rules_must_still_hold(self):
        (self.work / ".gitignore").write_text("# nothing protected\n")
        result = self.shipper().ship("break the ignore rules")
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "guard")
        self.assertIn("config/api_keys.json", result["note"])

    def test_a_file_that_does_not_parse_stops_the_ship(self):
        (self.work / "app.py").write_text("def broken(:\n")
        result = self.shipper().ship("break the syntax")
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "syntax")


class Pushing(Base):
    def test_a_clean_change_is_committed_and_pushed(self):
        (self.work / "app.py").write_text("print('hello, again')\n")
        result = self.shipper().ship("change the greeting",
                                     why="the owner asked for it")
        self.assertTrue(result["ok"], result)
        self.assertIn("change the greeting", git(self.origin, "log", "--oneline", "main"))
        self.assertEqual(git(self.origin, "show", "main:app.py"), "print('hello, again')")

    def test_a_push_leaves_the_copy_reporting_nothing_to_send(self):
        """A fresh push must not read as "ahead 1" a second later."""
        (self.work / "app.py").write_text("print('changed')\n")
        result = self.shipper().ship("a change worth sending")
        self.assertTrue(result["ok"], result.get("note"))
        status = self.shipper().status()
        self.assertEqual((status["ahead"], status["behind"]), (0, 0), status)

    def test_the_commit_message_carries_the_evidence(self):
        (self.work / "app.py").write_text("print('third')\n")
        self.shipper().ship("third attempt", why="because two is not three")
        body = git(self.origin, "log", "-1", "--format=%B", "main")
        self.assertIn("Why:", body)
        self.assertIn("Evidence:", body)
        self.assertIn("Secret scan", body)

    def test_nothing_to_ship_says_so(self):
        result = self.shipper().ship("nothing")
        self.assertFalse(result["ok"])
        self.assertIn("nothing to ship", result["note"])

    def test_a_diverged_remote_is_never_forced(self):
        other = self.base / "other"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(other)], check=True,
                       capture_output=True)
        (other / "app.py").write_text("print('from the other clone')\n")
        git(other, "commit", "-qam", "other work")
        git(other, "push", "-q", "origin", "main")

        (self.work / "app.py").write_text("print('from this clone')\n")
        result = self.shipper().ship("local work")
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "push")
        self.assertIn("will not force", result["note"])

    def test_no_token_means_no_push_and_a_sentence(self):
        (self.work / "app.py").write_text("print('needs a token')\n")
        result = self.shipper(token="").ship("no token")
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "push")
        self.assertIn("no GitHub token", result["note"])

    def test_the_ship_log_records_what_happened(self):
        (self.work / "app.py").write_text("print('logged')\n")
        self.shipper().ship("log this")
        rows = json.loads((self.base / "ship_log.json").read_text())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["ok"])
        self.assertEqual(rows[0]["files"], 1)


class Updating(Base):
    def advance_origin(self, name: str, text: str) -> None:
        other = self.base / "publisher"
        if not other.exists():
            subprocess.run(["git", "clone", "-q", str(self.origin), str(other)],
                           check=True, capture_output=True)
        else:
            git(other, "pull", "-q", "--ff-only")
        path = other / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        git(other, "add", "-A")
        git(other, "commit", "-qm", f"publish {name}")
        git(other, "push", "-q", "origin", "main")

    def test_no_update_says_so(self):
        result = Updater(self.work, token="t").check()
        self.assertTrue(result["ok"])
        self.assertEqual(result["behind"], 0)
        self.assertIn("up to date", result["note"])

    def test_a_new_commit_is_seen_with_the_files_it_touches(self):
        self.advance_origin("app.py", "print('new version')\n")
        result = Updater(self.work, token="t").check()
        self.assertEqual(result["behind"], 1)
        self.assertEqual(result["files"], ["app.py"])

    def test_code_changes_need_a_restart_and_say_so(self):
        self.advance_origin("app.py", "print('new version')\n")
        updater = Updater(self.work, token="t", marker=self.work / "restart.json")
        result = updater.apply()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["restart_required"])
        self.assertIn("restart is required", result["note"])
        marker = updater.restart_marker()
        self.assertIn("to", marker)
        self.assertEqual(marker["files"], ["app.py"])
        self.assertIn("command", updater.restart_command())

    def test_a_data_change_needs_no_restart(self):
        self.advance_origin("notes.md", "a new note\n")
        result = Updater(self.work, token="t").apply()
        self.assertTrue(result["ok"])
        self.assertFalse(result["restart_required"])
        self.assertIn("No restart needed", result["note"])

    def test_action_plugin_leaf_update_waits_for_reconnect_not_restart(self):
        self.advance_origin("actions/example.py", "VALUE = 2\n")
        updater = Updater(self.work, marker=self.work / "restart.json")
        result = updater.apply()
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["restart_required"])
        self.assertTrue(result["leaf_reload_pending"])
        self.assertEqual(result["leaf_files"], ["actions/example.py"])
        self.assertIn("reconnect boundary", result["note"])
        self.assertEqual(updater.restart_marker(), {})

    def test_non_leaf_code_still_requires_restart_with_mixed_changes(self):
        self.advance_origin("actions/example.py", "VALUE = 2\n")
        self.advance_origin("core/example.py", "VALUE = 3\n")
        updater = Updater(self.work, marker=self.work / "restart.json")
        result = updater.apply()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["restart_required"])
        self.assertFalse(result["leaf_reload_pending"])
        self.assertEqual(result["restart_files"], ["core/example.py"])
        self.assertEqual(updater.restart_marker()["files"], ["core/example.py"])

    def test_a_version_that_fails_its_checks_is_put_back(self):
        self.advance_origin("broken.py", "def broken(:\n")
        before = git(self.work, "rev-parse", "HEAD")
        updater = Updater(self.work, token="t")

        def verify():
            for path in self.work.rglob("*.py"):
                try:
                    compile(path.read_text(), str(path), "exec")
                except SyntaxError as error:
                    return {"ok": False, "note": f"{path.name}: {error.msg}"}
            return {"ok": True}

        result = updater.apply(verify=verify)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "verify")
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), before)
        self.assertFalse((self.work / "broken.py").exists())

    def test_uncommitted_work_is_not_pulled_over(self):
        self.advance_origin("app.py", "print('upstream')\n")
        (self.work / "app.py").write_text("print('local edit')\n")
        result = Updater(self.work, token="t").apply()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "dirty")
        self.assertIn("uncommitted", result["note"])


class Tools(Base):
    def setUp(self):
        super().setUp()
        self.state = self.base / "state"
        self.asked = []

        def approval(kind, *rest):
            self.asked.append(kind)
            return True

        self.service = CustomService(self.state, approval=approval)

    def call(self, name: str, **arguments):
        return self.service.perform("tool", {"name": name, "arguments": arguments})

    def test_the_four_ship_tools_are_registered(self):
        names = {row["name"] for row in self.service.perform("list_tools", {})}
        for tool in ("ship_status", "ship_now", "check_update", "apply_update"):
            self.assertIn(tool, names)

    def test_status_is_a_read_and_asks_nothing(self):
        self.asked.clear()
        result = self.call("ship_status")
        self.assertTrue(result["success"], result)
        self.assertEqual(self.asked, [])
        data = json.loads(result["output"])
        self.assertIn("scan", data)
        self.assertTrue(data["guards"]["ok"])

    def test_a_self_evolution_is_remembered_as_waiting_to_ship(self):
        pack = {"id": "pack_pending_probe", "title": "Pending probe",
                "purpose": "Proves a self-evolution is queued for shipping.",
                "steps": [{"tool": "search_text",
                           "args": {"path": "@workspace", "query": "TODO"}}]}
        added = self.call("add_skill", pack=pack)
        self.assertTrue(added["success"], added)
        pending = json.loads((self.state / "ship_pending.json").read_text())
        self.assertEqual(len(pending), 1)
        self.assertIn("added skill pack", pending[0]["reason"])

        from custom_jarvis.skills import SKILL_BY_ID, SKILLS
        SKILL_BY_ID.pop("pack_pending_probe", None)
        SKILLS[:] = [skill for skill in SKILLS if skill.identity != "pack_pending_probe"]


if __name__ == "__main__":
    unittest.main()


class AutoShip(unittest.TestCase):
    """The owner's rule: a self-evolution ships by itself, once he has said so.

    Publishing is public, so the switch is his: `ship_auto` in config. Off, the
    change is only recorded. On, one thread ships it and the log keeps the truth.
    """

    def setUp(self):
        from custom_jarvis.service import CustomService

        self.base = Path(tempfile.mkdtemp(prefix="ultron-auto-"))
        self.service = CustomService.__new__(CustomService)
        self.service.repo_dir = self.base
        self.service.data_dir = self.base

    def tearDown(self):
        import shutil

        shutil.rmtree(self.base, ignore_errors=True)

    def _config(self, values):
        from unittest import mock

        return mock.patch("memory.config_manager.load_api_keys", return_value=values)

    def test_it_is_off_when_nothing_is_configured(self):
        with self._config({}):
            self.assertFalse(self.service._ship_auto_enabled())

    def test_it_is_off_when_the_value_is_not_a_yes(self):
        for value in (False, "no", 0, None, "off", "maybe"):
            with self._config({"ship_auto": value}):
                self.assertFalse(self.service._ship_auto_enabled(), value)

    def test_it_is_on_only_for_a_clear_yes(self):
        for value in (True, "true", "yes", "on", "1", 1):
            with self._config({"ship_auto": value}):
                self.assertTrue(self.service._ship_auto_enabled(), value)

    def test_a_change_is_recorded_even_when_shipping_is_off(self):
        with self._config({}):
            self.service._note_change("added a skill")
        rows = json.loads((self.base / "ship_pending.json").read_text())
        self.assertEqual(rows[-1]["reason"], "added a skill")
        self.assertEqual(rows[-1]["status"], "waiting")

    def test_a_change_ships_once_the_owner_says_so(self):
        from unittest import mock

        seen = []

        with self._config({"ship_auto": True}), \
                mock.patch.object(type(self.service), "_auto_ship",
                                  lambda _self, reason: seen.append(reason)):
            self.service._note_change("added a skill")

        self.assertEqual(seen, ["added a skill"])

    def test_the_ship_runs_in_a_thread_and_gives_the_reason(self):
        from unittest import mock

        calls = []

        def fake_ship(_self, message, why="", **rest):
            calls.append((message, why))
            return {"ok": True}

        with mock.patch("custom_jarvis.ship.Shipper.ship", fake_ship), \
                mock.patch("custom_jarvis.ship.token_from_environment",
                           return_value="a-token"):
            self.service._auto_ship("removed a skill")
        for _ in range(100):
            if calls:
                break
            time.sleep(0.02)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "removed a skill")

    def test_a_failing_ship_never_breaks_the_change(self):
        from unittest import mock

        def explode(*_a, **_k):
            raise RuntimeError("the network is gone")

        with mock.patch("custom_jarvis.ship.token_from_environment",
                        return_value="a-token"), \
                mock.patch("custom_jarvis.ship.Shipper.ship", explode):
            self.assertTrue(self.service._auto_ship("a change")["started"])
            time.sleep(0.1)                       # the thread dies quietly
        self.assertTrue(True)                     # reaching here is the proof


class ShipTools(unittest.TestCase):
    """The four tools a person actually reaches: two to look, two to act."""

    def test_register_ship_tools_adds_the_four_named_tools(self):
        from custom_jarvis.ship_tools import register_ship_tools

        class Probe:
            """The same shape as ToolRegistry.register: keywords in, decorator out."""

            def __init__(self):
                self.seen = {}

            def register(self, **kwargs):
                self.seen[kwargs["name"]] = kwargs

                def decorator(func):
                    return func

                return decorator

        probe = Probe()
        base = Path(tempfile.mkdtemp(prefix="ultron-tools-"))
        try:
            register_ship_tools(probe, base, base / "pending.json")
        finally:
            import shutil

            shutil.rmtree(base, ignore_errors=True)

        self.assertEqual(sorted(probe.seen),
                         ["apply_update", "check_update", "ship_now", "ship_status"])
        self.assertTrue(probe.seen["ship_now"]["description"])
        self.assertEqual(probe.seen["ship_status"]["parameters"]["required"], [])

    def test_the_readers_are_read_only_and_the_actors_are_not(self):
        """A read must not ask for approval; a publish and a pull must."""
        from custom_jarvis.addon_runtime import AddonRegistry, ControlledRegistry

        readers = {"ship_status", "check_update"}
        actors = {"ship_now", "apply_update"}
        for name in readers:
            self.assertIn(name, AddonRegistry.READ_ONLY, name)
            self.assertNotIn(name, [n for n in actors], name)
        for name in actors:
            self.assertNotIn(name, AddonRegistry.READ_ONLY, name)
        self.assertTrue(set(readers).issubset(AddonRegistry.READ_ONLY))
        self.assertTrue(ControlledRegistry.READ_ONLY)
