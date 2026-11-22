"""The AST guardian against renaming, building a name out of pieces, and odd paths.

`core/ast_guardian.py` blocked `import subprocess` and `os.system(...)` — written exactly
that way. Twelve of fourteen ways of saying the same thing went through (measured):
`import os as o`, `from os import system`, `import builtins as b; b.exec(...)`,
`getattr((), '__cl' + 'ass__')`, a bare `__builtins__`, `os.execv`, `os.startfile`,
asyncio's subprocess, `sys.modules['subprocess']`, `multiprocessing`, `runpy`. And the
referee list was compared as an exact string, so `./core/policy.py`, `core//policy.py`
and `CORE/policy.py` were not "core/policy.py" (the last is the same file on Windows).

Each case below states what it is; the second class is the cost: ordinary code that must
still pass, so the tightening does not turn into blocking everything.
"""

from __future__ import annotations

import unittest

from core.ast_guardian import ASTGuardian

PATH = "plugins/example.py"


def audit(source: str, path: str = PATH):
    return ASTGuardian().audit_source(source, path)


def rules(source: str, path: str = PATH) -> set[str]:
    return {v.rule for v in audit(source, path).violations}


BLOCKED = {
    "plain os.system": "import os\nos.system('calc')\n",
    "import os as o": "import os as o\no.system('calc')\n",
    "from os import system": "from os import system\nsystem('calc')\n",
    "from os import system as run": "from os import system as run\nrun('calc')\n",
    "os.popen through an alias": "import os as operating\noperating.popen('dir')\n",
    "os.startfile": "import os\nos.startfile('x.exe')\n",
    "os.execv": "import os\nos.execv('/bin/sh', ['sh'])\n",
    "os.execvp through an alias": "from os import execvp as go\ngo('sh', ['sh'])\n",
    "os.spawnl": "import os\nos.spawnl(os.P_NOWAIT, 'x')\n",
    "os.fork": "import os\nos.fork()\n",
    "os.posix_spawn": "import os\nos.posix_spawn('/bin/sh', ['sh'], {})\n",
    "import subprocess": "import subprocess\nsubprocess.run(['calc'])\n",
    "subprocess.check_output": "import subprocess as sp\nsp.check_output(['x'])\n",
    "from subprocess import Popen": "from subprocess import Popen\nPopen('x')\n",
    "asyncio subprocess": "import asyncio\nasyncio.create_subprocess_shell('calc')\n",
    "asyncio subprocess, aliased": "import asyncio as a\na.create_subprocess_exec('x')\n",
    "runpy": "import runpy\nrunpy.run_path('/tmp/x.py')\n",
    "runpy, from-import": "from runpy import run_module\nrun_module('x')\n",
    "multiprocessing": "import multiprocessing\nmultiprocessing.Process(target=print).start()\n",
    "pty": "import pty\npty.spawn('/bin/sh')\n",
    "code": "import code\ncode.interact()\n",
    "marshal": "import marshal\nmarshal.loads(b'')\n",
    "eval": "eval('1+1')\n",
    "exec": "exec('x=1')\n",
    "compile": "compile('1', 'f', 'eval')\n",
    "__import__": "__import__('os')\n",
    "builtins.exec": "import builtins\nbuiltins.exec('x=1')\n",
    "builtins.exec through an alias": "import builtins as b\nb.exec('print(1)')\n",
    "from builtins import eval as e": "from builtins import eval as e\ne('1')\n",
    "getattr with a dunder": "x = getattr((), '__class__')\n",
    "getattr with a name built from pieces": "x = getattr((), '__cl' + 'ass__')\n",
    "getattr with an f-string of literals": "x = getattr((), f\"__cl{'ass'}__\")\n",
    "setattr with a dunder": "setattr(f, '__code__', g.__code__)\n",
    "hasattr probing a frame": "hasattr(e, 'tb_frame')\n",
    "bare __builtins__": "b = __builtins__\nb['ex' + 'ec']('print(1)')\n",
    "sys.modules subscript": "import sys\nsys.modules['subprocess'].run(['calc'])\n",
    "sys.modules subscript built from pieces": "import sys\nsys.modules['sub' + 'process'].run(['x'])\n",
    "sys.modules.get": "import sys\nsys.modules.get('subprocess').run(['x'])\n",
    "sys.modules through from-import": "from sys import modules\nmodules['ctypes']\n",
    "frames": "import sys\nsys._getframe().f_back.f_globals\n",
    "__subclasses__": "x = object.__subclasses__()\n",
    "class walk": "x = ().__class__.__bases__[0].__subclasses__()\n",
    "socket": "import socket\nsocket.socket()\n",
    "ctypes": "import ctypes\nctypes.windll\n",
    # A name reused for something harmless must not hide the dangerous reading of it. The alias table
    # kept only the LAST binding of a name, and its docstring said that "can only over-report".
    "an alias reused inside a function": ("import os as o\ndef f():\n    import json as o\n"
                                          "    return o.dumps({})\no.system('calc')\n"),
    "a name rebound by a later import": "from json import decoder as os\nimport os\nos.system('calc')\n",
    "the harmless binding comes last": "import os as o\nimport json as o\no.system('calc')\n",
    # Naming a forbidden callable is refused as well as calling it.
    "assigned to a name": "import os\nrun = os.system\nrun('calc')\n",
    "a builtin assigned to a name": "e = eval\ne('1+1')\n",
    "a chain of names, in either order": "import os\nb = a\na = os.system\nb('x')\n",
    "annotated assignment": "import os\nrun: object = os.system\n",
    "walrus": "import os\nif (run := os.system):\n    run('x')\n",
    "handed to map": "import os\nlist(map(os.system, ['calc']))\n",
    "stored in a dict": "import os\nTABLE = {'run': os.system}\n",
    "a builtin in a list": "handlers = [eval]\n",
    "through its own __call__": "import os\nos.system.__call__('calc')\n",
    "returned": "import os\ndef f():\n    return os.popen\n",
    "a renamed module, not called": "import subprocess as sp\nf = sp.run\n",
    # a module renamed by plain assignment, and a wildcard import
    "a module assigned to a name": "import os\nm = os\nm.system('calc')\n",
    "builtins assigned to a name": "import builtins\nb = builtins\nb.exec('x=1')\n",
    "a module assigned twice over": "import os\nm = os\nn = m\nn.popen('dir')\n",
    "from os import *": "from os import *\nsystem('calc')\n",
    "from asyncio import *": "from asyncio import *\n",
    "from builtins import *": "from builtins import *\neval('1')\n",
    # getattr naming the callable
    "getattr with a callable's name": "import os\ngetattr(os, 'system')('calc')\n",
    "getattr with a callable's name in pieces": "import os\ngetattr(os, 'sys' + 'tem')('x')\n",
    "getattr through an alias": "import os as o\ngetattr(o, 'popen')('x')\n",
    "getattr on builtins": "import builtins\ngetattr(builtins, 'exec')('x=1')\n",
}

ALLOWED = {
    "plain os use": "import os\np = os.path.join('a', 'b')\ne = os.environ.get('X')\nc = os.getcwd()\n",
    "from os import path": "from os import path\nx = path.exists('/')\n",
    "os aliased and used harmlessly": "import os as o\nx = o.getpid()\n",
    "a local named system": "def system(x):\n    return x\nsystem(1)\n",
    "a method called exec": "class C:\n    def exec(self, x):\n        return x\nC().exec(1)\n",
    "a method called run on an object": "def f(job):\n    return job.run()\n",
    "getattr with a plain constant": "x = getattr(obj, 'LIVE_MODEL', None)\n",
    "getattr with an f-string (a dispatcher)": "def f(self, kind):\n    return getattr(self, f'_handle_{kind}')()\n",
    "getattr with a variable": "def f(o, name):\n    return getattr(o, name)\n",
    "sys.modules.get of an ordinary module": "import sys\nm = sys.modules.get('main')\n",
    "sys.modules subscript of an ordinary module": "import sys\nm = sys.modules['json']\n",
    "network and disk are not judged": ("import urllib.request\nimport shutil\n"
                                         "urllib.request.urlopen('http://example.com')\n"
                                         "shutil.rmtree('/tmp/x')\nopen('f').read()\n"),
    "a relative import of a sibling named code": "from .code import thing\nfrom . import subprocess_helpers\n",
    "dunders that are not dangerous": "class C:\n    def __init__(self):\n        self.__dict__['a'] = 1\n"
                                      "    def __repr__(self):\n        return '<C>'\n",
    "__name__ and __file__": "from pathlib import Path\nhere = Path(__file__).parent\nif __name__ == '__main__':\n    pass\n",
    "ordinary dataclass code": "from dataclasses import dataclass\n@dataclass\nclass P:\n    x: int = 0\n",
    "one name bound to two harmless things": ("import json as o\ndef f():\n    import csv as o\n"
                                              "    return o.reader\nx = o.dumps({})\n"),
    "a harmless callable assigned and called": "import os\ncwd = os.getcwd\nprint(cwd())\n",
    "a harmless callable handed to map": "import os\nnames = list(map(os.path.basename, ['/a/b']))\n",
    "a chain of harmless names": "import os\na = os.path.join\nb = a\nb('x', 'y')\n",
    "getattr with a harmless module attribute": "import os\nsep = getattr(os, 'sep')\n",
    "a docstring that mentions the forbidden call": '"""Do not call os.system or eval here."""\nx = 1\n',
    "a string that names it": "NAMES = ['os.system', 'eval', 'subprocess.run']\n",
    "a comment that names it": "import os\n# os.system('x') would be refused\nx = os.getpid()\n",
    "a keyword called exec": "def f(**kw):\n    return kw\nf(exec=True, eval=False)\n",
    "an attribute called eval on an object": "def f(model):\n    return model.eval()\n",
    "an attribute called compile on a module": "import re\nrx = re.compile('a')\nrx.match('a')\n",
    "socket named in an annotation of an unrelated name": "import sock\nx: sock.Socket = None\n",
    "a wildcard import from a module with nothing forbidden in it": "from os.path import *\nfrom typing import *\n",
    "a module assigned to a name and used harmlessly": "import os\nm = os\nx = m.getpid()\n",
}


class WhatIsBlocked(unittest.TestCase):
    def test_every_way_of_saying_it(self):
        for name, source in BLOCKED.items():
            with self.subTest(name):
                self.assertFalse(audit(source).approved, f"{name} went through")

    def test_each_block_names_a_rule_and_a_line(self):
        for name, source in BLOCKED.items():
            with self.subTest(name):
                blockers = [v for v in audit(source).violations if v.severity == "BLOCK"]
                self.assertTrue(blockers)
                for violation in blockers:
                    self.assertTrue(violation.rule)
                    self.assertGreaterEqual(violation.line, 1)

    def test_the_rule_names_for_the_common_cases_are_stable(self):
        self.assertIn("FORBIDDEN_CALL", rules("import os as o\no.system('x')\n"))
        self.assertIn("FORBIDDEN_BUILTIN", rules("eval('1')\n"))
        self.assertIn("FORBIDDEN_IMPORT", rules("import runpy\n"))
        self.assertIn("DUNDER_MANIPULATION", rules("x = getattr((), '__cl' + 'ass__')\n"))


class WhatIsStillAllowed(unittest.TestCase):
    def test_ordinary_code_passes(self):
        for name, source in ALLOWED.items():
            with self.subTest(name):
                report = audit(source)
                self.assertTrue(report.approved,
                                f"{name} was blocked: {[(v.rule, v.detail) for v in report.violations]}")


class TheRefereeIsRecognisedWhateverItsSpelling(unittest.TestCase):
    SPELLINGS = ["core/policy.py", "./core/policy.py", "core//policy.py", "CORE/policy.py",
                 "core/Policy.PY", "core/../core/policy.py", "core\\policy.py",
                 ".\\core\\policy.py", "/home/someone/project/core/policy.py",
                 "C:/Users/someone/project/core/policy.py", "C:\\Users\\x\\core\\confirm.py",
                 "core/ast_guardian.py", "scripts/proof_gate.py", "config/api_keys.json"]

    def test_each_spelling_is_a_referee_file(self):
        for path in self.SPELLINGS:
            with self.subTest(path=path):
                report = audit("x = 1\n", path)
                self.assertFalse(report.approved)
                self.assertEqual(report.violations[0].rule, "REFEREE_IMMUTABILITY")

    def test_a_different_file_with_a_similar_name_is_not(self):
        for path in ("plugins/core/policy.py", "core/policy_notes.py", "core/policy.pyc",
                     "docs/core/policy.py", "mycore/policy.py", "core/policies.py",
                     "plugins/example.py"):
            with self.subTest(path=path):
                self.assertTrue(audit("x = 1\n", path).approved, path)


class AReusedNameHidesNothing(unittest.TestCase):
    """Every binding of a name is kept, so a second one can add a reading and never remove one."""

    def test_the_order_of_the_bindings_does_not_matter(self):
        first = "import os as o\nimport json as o\no.system('x')\n"
        second = "import json as o\nimport os as o\no.system('x')\n"
        self.assertFalse(audit(first).approved)
        self.assertFalse(audit(second).approved)

    def test_one_violation_per_call_however_many_readings(self):
        source = "import os as o\nimport json as o\no.system('x')\n"
        blockers = [v for v in audit(source).violations if v.severity == "BLOCK"]
        self.assertEqual(len(blockers), 1, [(v.rule, v.line, v.detail) for v in blockers])

    def test_a_call_is_not_reported_twice_as_a_call_and_a_reference(self):
        blockers = [v for v in audit("import os\nos.system('x')\n").violations if v.severity == "BLOCK"]
        self.assertEqual(len(blockers), 1)

    def test_a_reference_names_what_it_found(self):
        report = audit("import os\nrun = os.system\n")
        details = [v.detail for v in report.violations if v.severity == "BLOCK"]
        self.assertEqual(len(details), 1)
        self.assertIn("named here without being called", details[0])
        self.assertIn("os.system", details[0])

    def test_assigning_twice_does_not_loop_or_slow_down(self):
        source = "\n".join(f"v{i} = v{i - 1}" for i in range(1, 400)) + "\nv0 = 1\n"
        self.assertTrue(audit(source).approved)


class TheLimitsTheHeaderNames(unittest.TestCase):
    """The module header lists what the guardian cannot read through. This pins that list to what the
    code does, so the header cannot go on saying something the code no longer (or never did) do.
    If one of these starts being refused, move it from the header's `cannot` sentence to its `can`.
    """

    def test_a_name_built_from_data_is_not_judged(self):
        self.assertTrue(audit("def f(o, name):\n    return getattr(o, name)\n").approved)

    def test_a_value_taken_out_of_a_namespace_without_an_attribute_is_not_judged(self):
        self.assertTrue(audit("import os\nvars(os)['system']('x')\n").approved)
        self.assertTrue(audit("import os\nos.__dict__['system']('x')\n").approved)

    def test_a_builtin_name_used_for_something_else_is_refused_which_is_over_reporting(self):
        report = audit("def f(compile):\n    return compile\n")
        self.assertFalse(report.approved)
        self.assertIn("FORBIDDEN_BUILTIN", {v.rule for v in report.violations})

    def test_a_module_carried_through_a_container_or_a_return_is_not_followed(self):
        self.assertTrue(audit("import os\nmods = [os]\nmods[0].system('x')\n").approved)
        self.assertTrue(audit("import os\ndef f():\n    return os\nf().system('x')\n").approved)
        self.assertTrue(audit("import os\nclass K:\n    mod = os\nK.mod.system('x')\n").approved)
        self.assertTrue(audit("import os\nglobals()['os'].system('x')\n").approved)

    def test_a_module_reached_as_an_attribute_of_another_is_not_followed(self):
        self.assertTrue(audit("import shutil\nshutil.os.system('x')\n").approved)
        self.assertTrue(audit("import os.path as p\np.os.system('x')\n").approved)

    def test_a_lookup_done_by_another_function_is_not_followed(self):
        self.assertTrue(audit("import os, operator\noperator.attrgetter('system')(os)('x')\n").approved)

    def test_the_header_names_each_limit_these_tests_pin(self):
        from core import ast_guardian
        header = " ".join(ast_guardian.__doc__.split())
        for phrase in ("a name built from data", "[os][0].system", "shutil.os.system",
                       "operator.attrgetter", "vars(os)['system']", "os.__dict__['system']",
                       "over-report", "from os import *"):
            self.assertIn(phrase, header)

    def test_nothing_in_the_file_says_the_alias_table_can_only_over_report(self):
        # It was false: a name bound twice kept only its last meaning, which could hide the
        # dangerous one. The guardian has no sentence of that shape now, in code or comment.
        import inspect
        from core import ast_guardian
        source = inspect.getsource(ast_guardian)
        self.assertFalse("can only over-report" in source, "the false sentence is back in core/ast_guardian.py")


class ThePublicSurfaceIsUnchanged(unittest.TestCase):
    def test_the_names_other_code_may_import_are_still_there(self):
        from core import ast_guardian as g
        for name in ("Violation", "ASTAuditReport", "ASTGuardian", "FORBIDDEN_CALL_PATTERNS",
                     "FORBIDDEN_IMPORT_MODULES", "REFEREE_FILES"):
            self.assertTrue(hasattr(g, name), name)

    def test_the_report_still_carries_the_hash_and_path(self):
        report = audit("x = 1\n", "plugins/a.py")
        self.assertEqual(report.file_path, "plugins/a.py")
        self.assertEqual(len(report.source_hash), 64)

    def test_a_syntax_error_is_still_reported_not_raised(self):
        report = audit("def broken(:\n")
        self.assertEqual(report.violations[0].rule, "SYNTAX_ERROR")


if __name__ == "__main__":
    unittest.main()
