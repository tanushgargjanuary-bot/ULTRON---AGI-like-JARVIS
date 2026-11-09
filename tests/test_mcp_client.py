"""One adaptor instead of two hundred integrations. These tests talk to a real server.

The server is a small Python program written into a temporary folder, speaking the
protocol on its standard input and output. Nothing is mocked: the handshake, the tool
list, the call and the shutdown all cross a real pipe, because that is where this kind
of client actually breaks.
"""

import json
import os
import signal
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

from core import policy
from custom_jarvis import mcp_client
from custom_jarvis.mcp_client import Client, McpError

SERVER = textwrap.dedent(
    '''
    import json, sys, time

    TOOLS = [
        {"name": "add", "description": "Add two numbers.",
         "inputSchema": {"type": "OBJECT",
                         "properties": {"a": {"type": "NUMBER"}, "b": {"type": "NUMBER"}},
                         "required": ["a", "b"]}},
        {"name": "shout", "description": "Say a thing loudly.",
         "inputSchema": {"type": "OBJECT", "properties": {"text": {"type": "STRING"}}}},
    ]

    def reply(identity, result=None, error=None):
        message = {"jsonrpc": "2.0", "id": identity}
        if error:
            message["error"] = error
        else:
            message["result"] = result
        sys.stdout.write(json.dumps(message) + "\\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        method = request.get("method")
        identity = request.get("id")
        if method == "initialize":
            reply(identity, {"protocolVersion": "2024-11-05", "capabilities": {},
                             "serverInfo": {"name": "fake", "version": "1"}})
        elif method == "tools/list":
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/message",
                                         "params": {"level": "info"}}) + "\\n")
            reply(identity, {"tools": TOOLS})
        elif method == "tools/call":
            params = request.get("params") or {}
            if params.get("name") == "add":
                a = (params.get("arguments") or {}).get("a", 0)
                b = (params.get("arguments") or {}).get("b", 0)
                reply(identity, {"content": [{"type": "text", "text": str(a + b)}]})
            else:
                reply(identity, {"isError": True,
                                 "content": [{"type": "text", "text": "unknown tool"}]})
        elif identity is not None:
            reply(identity, error={"code": -32601, "message": "no such method"})
    '''
)

SILENT = textwrap.dedent(
    '''
    import sys, time
    for line in sys.stdin:
        time.sleep(5)          # reads, answers nothing
    '''
)

DIES = textwrap.dedent(
    '''
    import sys
    sys.stdin.readline()
    sys.exit(3)               # dies in the middle of the handshake
    '''
)


class _Folder(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.folder = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def script(self, body: str, name: str = "server.py") -> str:
        path = self.folder / name
        path.write_text(body, encoding="utf-8")
        return str(path)

    def entry(self, body: str = SERVER, **extra) -> dict:
        row = {"name": "fake", "command": sys.executable, "args": [self.script(body)]}
        row.update(extra)
        return row

    def config(self, servers) -> None:
        path = self.folder / mcp_client.CONFIG_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"servers": servers}), encoding="utf-8")


class TheConfigFile(_Folder):
    def test_no_file_means_no_servers_and_no_error(self):
        self.assertEqual(mcp_client.load_config(self.folder), [])

    def test_a_plain_entry_is_read(self):
        self.config([{"name": "files", "command": sys.executable, "args": ["-m", "thing"]}])
        rows = mcp_client.load_config(self.folder)
        self.assertEqual(rows[0]["command"], sys.executable)
        self.assertEqual(rows[0]["args"], ["-m", "thing"])

    def test_a_url_is_refused_because_this_is_a_local_client(self):
        self.config([{"name": "web", "command": "x", "args": [], "url": "http://localhost:9"}])
        with self.assertRaises(McpError) as caught:
            mcp_client.load_config(self.folder)
        self.assertIn("local program only", str(caught.exception))

    def test_a_command_with_a_space_is_refused_not_run_through_a_shell(self):
        self.config([{"name": "bad", "command": "python -m thing", "args": []}])
        with self.assertRaises(McpError) as caught:
            mcp_client.load_config(self.folder)
        self.assertIn("space in its command", str(caught.exception))

    def test_a_nameless_server_is_refused(self):
        self.config([{"name": "..", "command": "x", "args": []}])
        with self.assertRaises(McpError):
            mcp_client.load_config(self.folder)

    def test_args_must_be_strings(self):
        self.config([{"name": "bad", "command": "x", "args": [1]}])
        with self.assertRaises(McpError):
            mcp_client.load_config(self.folder)

    def test_broken_json_says_so_in_one_sentence(self):
        path = self.folder / mcp_client.CONFIG_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{oops", encoding="utf-8")
        with self.assertRaises(McpError) as caught:
            mcp_client.load_config(self.folder)
        self.assertIn("not valid JSON", str(caught.exception))


class TheFakeServer(_Folder):
    def setUp(self):
        super().setUp()
        self.client = Client(self.entry(), timeout=10.0)

    def tearDown(self):
        self.client.close()
        super().tearDown()

    def test_two_tools_come_back_with_prefixed_names(self):
        self.client.start()
        names = [row["name"] for row in self.client.declarations()]
        self.assertEqual(names, ["mcp_fake_add", "mcp_fake_shout"])

    def test_a_declaration_is_what_the_loader_reads(self):
        self.client.start()
        row = self.client.declarations()[0]
        self.assertEqual(row["parameters"]["type"], "OBJECT")
        self.assertIn("a", row["parameters"]["properties"])
        self.assertTrue(callable(row["handler"]))
        self.assertTrue(row["description"])

    def test_a_call_reaches_the_server_and_comes_back_as_text(self):
        self.client.start()
        handler = self.client.declarations()[0]["handler"]
        self.assertEqual(handler({"a": 2, "b": 3}),
                         mcp_client.UNTRUSTED_PREFIX + "5")

    def test_an_error_answer_is_reported_not_raised(self):
        self.client.start()
        handler = self.client.declarations()[1]["handler"]
        self.assertEqual(handler({"text": "hi"}),
                         mcp_client.UNTRUSTED_PREFIX + "unknown tool")

    def test_server_text_is_labelled_as_untrusted(self):
        self.client.start()
        handler = self.client.declarations()[0]["handler"]
        self.assertTrue(handler({"a": 2, "b": 3}).startswith(
            mcp_client.UNTRUSTED_PREFIX))

    def test_a_notification_between_replies_is_not_mistaken_for_one(self):
        self.client.start()          # the fake server prints one before tools/list
        self.assertEqual(len(self.client.list_tools()), 2)

    def test_the_name_can_never_shadow_a_native_tool(self):
        self.assertEqual(mcp_client.tool_name("fake", "read_file"), "mcp_fake_read_file")
        self.assertEqual(mcp_client.tool_name("Fake Server", "a b"), "mcp_fake_server_a_b")


class TheSchema(unittest.TestCase):
    """A real server writes lower-case JSON Schema; this app speaks upper case."""

    def test_lower_case_types_are_made_upper_case(self):
        clean = mcp_client.schema(
            {"type": "object", "properties": {"where": {"type": "string"}}, "required": ["where"]}
        )
        self.assertEqual(clean["type"], "OBJECT")
        self.assertEqual(clean["properties"]["where"]["type"], "STRING")
        self.assertEqual(clean["required"], ["where"])

    def test_the_provider_receives_it_with_nothing_to_repair(self):
        from core.action_loader import sanitize_declarations

        clean = mcp_client.schema(
            {"type": "object",
             "properties": {"a": {"type": "number"}, "b": {"type": "boolean"}},
             "required": ["a"]}
        )
        _decls, repairs = sanitize_declarations(
            [{"name": "mcp_fake_add", "description": "x", "parameters": clean}]
        )
        self.assertEqual(repairs, [])

    def test_required_never_names_an_argument_that_does_not_exist(self):
        clean = mcp_client.schema(
            {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a", "ghost"]}
        )
        self.assertEqual(clean["required"], ["a"])

    def test_a_tool_with_no_arguments_stays_a_tool_with_no_arguments(self):
        clean = mcp_client.schema({"type": "object"})
        self.assertEqual(clean, {"type": "OBJECT", "properties": {}})

    def test_an_unknown_type_becomes_a_string(self):
        clean = mcp_client.schema({"type": "object", "properties": {"a": {"type": "whatever"}}})
        self.assertEqual(clean["properties"]["a"]["type"], "STRING")

    def test_object_shape_is_inferred_when_type_is_omitted(self):
        clean = mcp_client.schema({
            "properties": {"profile": {"properties": {"name": {"type": "string"}}}}
        })
        self.assertEqual(clean["type"], "OBJECT")
        self.assertEqual(clean["properties"]["profile"]["type"], "OBJECT")
        self.assertEqual(
            clean["properties"]["profile"]["properties"]["name"]["type"], "STRING"
        )

    def test_nested_object_properties_are_preserved(self):
        clean = mcp_client.schema({
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "integer"},
                    },
                    "required": ["name"],
                }
            },
        })
        user = clean["properties"]["user"]
        self.assertEqual(user["properties"]["name"]["type"], "STRING")
        self.assertEqual(user["properties"]["age"]["type"], "INTEGER")
        self.assertEqual(user["required"], ["name"])

    def test_array_of_objects_preserves_item_schema(self):
        clean = mcp_client.schema({
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                }
            },
        })
        item = clean["properties"]["files"]["items"]
        self.assertEqual(item["type"], "OBJECT")
        self.assertEqual(item["properties"]["path"]["type"], "STRING")
        self.assertEqual(item["required"], ["path"])

    def test_invalid_nested_properties_are_rejected_not_erased(self):
        with self.assertRaisesRegex(McpError, "invalid properties"):
            mcp_client.schema({
                "type": "object",
                "properties": {"user": {"type": "object", "properties": ["not", "a", "dict"]}},
            })

    def test_excessive_schema_nesting_is_rejected(self):
        node = {"type": "string"}
        for _ in range(mcp_client.MAX_SCHEMA_DEPTH + 1):
            node = {"type": "object", "properties": {"nested": node}}
        with self.assertRaisesRegex(McpError, "nesting limit"):
            mcp_client.schema({"type": "object", "properties": {"root": node}})

    def test_enum_values_keep_their_json_types(self):
        clean = mcp_client.schema({
            "type": "object",
            "properties": {"value": {"type": "number", "enum": [0, 1.5, True, False, "x"]}},
        })
        values = clean["properties"]["value"]["enum"]
        self.assertEqual(values, [0, 1.5, True, False, "x"])
        self.assertIs(type(values[0]), int)
        self.assertIs(type(values[2]), bool)
        self.assertIs(type(values[3]), bool)


class TheMcpNameRegistry(unittest.TestCase):
    def test_distinct_server_names_that_normalize_to_one_name_are_rejected(self):
        first_name = mcp_client.tool_name("files-prod", "list")
        second_name = mcp_client.tool_name("files_prod", "list")
        self.assertEqual(first_name, second_name)

        registry = {}
        collisions = set()
        first = {"name": first_name, "handler": lambda _args: "first"}
        second = {"name": second_name, "handler": lambda _args: "second"}

        self.assertIsNone(mcp_client.register_declaration(registry, collisions, first))
        message = mcp_client.register_declaration(registry, collisions, second)
        self.assertIn("collision", message)
        self.assertNotIn(first_name, registry)
        self.assertIn(first_name, collisions)

    def test_mcp_name_cannot_shadow_a_reserved_native_tool(self):
        name = mcp_client.tool_name("custom", "dangerous")
        registry = {}
        collisions = set()
        note = mcp_client.register_declaration(
            registry, collisions, {"name": name, "handler": lambda _args: "remote"},
            reserved_names={name},
        )
        self.assertIn("native tool", note)
        self.assertEqual(registry, {})
        self.assertIn(name, collisions)

    def test_a_third_duplicate_cannot_reintroduce_a_rejected_name(self):
        name = mcp_client.tool_name("files-prod", "list")
        registry = {}
        collisions = set()
        mcp_client.register_declaration(registry, collisions, {"name": name, "id": 1})
        mcp_client.register_declaration(registry, collisions, {"name": name, "id": 2})
        mcp_client.register_declaration(registry, collisions, {"name": name, "id": 3})
        self.assertNotIn(name, registry)
        self.assertIn(name, collisions)


class ThePolicyStaysThePolicy(_Folder):
    def test_a_new_tool_is_asked_about_because_policy_never_saw_it(self):
        decision = policy.classify("mcp_fake_add", {"a": 1})
        self.assertFalse(decision.allow, "an unknown name must not be allowed without asking")
        self.assertEqual(decision.tier, policy.Tier.GUARDED)

    def test_this_module_may_not_classify_its_own_tools(self):
        """Guard against MCP code bypassing the shared policy boundary."""
        source = Path(mcp_client.__file__).read_text(encoding="utf-8")
        for word in ("OBSERVE_TOOLS", "ROUTINE_TOOLS", "policy.grant", "set_workspace_roots"):
            self.assertNotIn(word, source,
                             "an adaptor that writes its own permissions is not an adaptor")


class ADyingServer(_Folder):
    def test_a_server_that_dies_during_the_handshake_is_one_sentence(self):
        client = Client(self.entry(DIES), timeout=5.0)
        try:
            with self.assertRaises(McpError):
                client.start()
        finally:
            client.close()

    def test_a_server_that_never_answers_times_out_instead_of_hanging_the_turn(self):
        client = Client(self.entry(SILENT), timeout=0.4)
        try:
            with self.assertRaisesRegex(McpError, "no answer"):
                client.start()
        finally:
            client.close()

    def test_context_entry_failure_closes_the_process(self):
        client = Client(self.entry(SILENT), timeout=0.2)
        with self.assertRaises(McpError):
            with client:
                self.fail("silent server unexpectedly entered the context")
        self.assertIsNone(client._process)
        self.assertFalse(client.alive())

    def test_context_cleanup_failure_does_not_mask_the_entry_error(self):
        client = Client(self.entry())
        original = McpError("handshake failed")
        with (
            mock.patch.object(client, "start", side_effect=original),
            mock.patch.object(client, "close", side_effect=OSError("cleanup failed")) as close,
        ):
            with self.assertRaises(McpError) as caught:
                with client:
                    self.fail("entry unexpectedly succeeded")
        self.assertIs(caught.exception, original)
        close.assert_called_once_with()

    def test_blocked_stdin_write_has_a_deadline_and_releases_its_worker(self):
        class BlockedStdin:
            def __init__(self):
                self.entered = threading.Event()
                self.released = threading.Event()
                self.finished = threading.Event()

            def write(self, _text):
                self.entered.set()
                self.released.wait(5.0)

            def flush(self):
                return None

            def close(self):
                self.released.set()

        class FakeProcess:
            pid = 123456

            def __init__(self):
                self.stdin = BlockedStdin()

            def poll(self):
                return None

        client = Client(self.entry(), timeout=2.0)
        process = FakeProcess()
        client._process = process
        original_write = process.stdin.write

        def tracked_write(text):
            try:
                return original_write(text)
            finally:
                process.stdin.finished.set()

        process.stdin.write = tracked_write
        with mock.patch.object(client, "_signal_tree"):
            started = time.monotonic()
            with self.assertRaisesRegex(McpError, "timed out writing"):
                client.request("blocked", {}, timeout=0.05)
            self.assertLess(time.monotonic() - started, 0.75)
        self.assertTrue(process.stdin.entered.is_set())
        self.assertTrue(process.stdin.finished.wait(1.0))
        client._process = None

    def test_closing_ends_the_process(self):
        client = Client(self.entry())
        client.start()
        process = client._process
        self.assertIsNotNone(process)
        client.close()
        self.assertIsNotNone(process.poll(), "the server must not outlive the app")

    @unittest.skipUnless(os.name == "posix", "POSIX process groups only")
    def test_close_signals_the_owned_process_group(self):
        class FakeProcess:
            pid = 4321
            stdin = stdout = stderr = None

            def wait(self, timeout):
                return None

        client = Client(self.entry())
        client._process = FakeProcess()
        with mock.patch.object(mcp_client.os, "killpg") as kill_group:
            client.close()
        self.assertEqual(kill_group.call_count, 2)
        self.assertEqual(kill_group.call_args_list[0].args, (4321, signal.SIGTERM))
        self.assertEqual(kill_group.call_args_list[1].args, (4321, signal.SIGKILL))

    def test_closing_twice_is_not_an_error(self):
        client = Client(self.entry())
        client.start()
        client.close()
        client.close()

    def test_a_command_that_is_not_installed_is_named_not_run(self):
        client = Client({"name": "gone", "command": "ultron-no-such-program", "args": []})
        with self.assertRaises(McpError) as caught:
            client.start()
        self.assertIn("was not found", str(caught.exception))


class TheWholeMachine(_Folder):
    def test_one_broken_entry_does_not_stop_the_others(self):
        self.config([
            {"name": "gone", "command": "ultron-no-such-program", "args": []},
            {"name": "fake", "command": sys.executable, "args": [self.script(SERVER)]},
        ])
        clients, notes = mcp_client.connect_all(self.folder)
        try:
            self.assertEqual(len(clients), 1)
            self.assertEqual(len(notes), 1)
            self.assertIn("was not found", notes[0])
            self.assertEqual(len(clients[0].list_tools()), 2)
        finally:
            mcp_client.close_all(clients)
        self.assertFalse(clients[0].alive(), "a closed client is not a running server")

    def test_a_declaration_handler_survives_the_client_being_closed(self):
        self.config([{"name": "fake", "command": sys.executable, "args": [self.script(SERVER)]}])
        clients, _ = mcp_client.connect_all(self.folder)
        row = clients[0].declarations()[0]
        mcp_client.close_all(clients)
        with self.assertRaises(McpError):
            row["handler"]({"a": 1, "b": 1})


if __name__ == "__main__":
    unittest.main()
