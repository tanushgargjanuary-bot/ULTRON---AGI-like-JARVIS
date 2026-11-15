import unittest
from core.ast_guardian import ASTGuardian


class TestASTGuardian(unittest.TestCase):
    def setUp(self):
        self.guardian = ASTGuardian()

    def test_benign_code_passes(self):
        code = "def calculate(a: int, b: int) -> int:\n    return a + b\n"
        report = self.guardian.audit_source(code, "plugins/calculator.py")
        self.assertTrue(report.approved)
        self.assertFalse(report.has_blockers)

    def test_referee_file_is_blocked(self):
        code = "print('hello')\n"
        report = self.guardian.audit_source(code, "core/policy.py")
        self.assertFalse(report.approved)
        self.assertTrue(report.has_blockers)
        self.assertEqual(report.violations[0].rule, "REFEREE_IMMUTABILITY")

    def test_forbidden_subprocess_import_blocked(self):
        code = "import subprocess\nsubprocess.run(['dir'])\n"
        report = self.guardian.audit_source(code, "plugins/bad_plugin.py")
        self.assertFalse(report.approved)
        rules = [v.rule for v in report.violations]
        self.assertIn("FORBIDDEN_IMPORT", rules)

    def test_forbidden_eval_blocked(self):
        code = "def run_dynamic(cmd):\n    return eval(cmd)\n"
        report = self.guardian.audit_source(code, "plugins/evaluator.py")
        self.assertFalse(report.approved)
        rules = [v.rule for v in report.violations]
        self.assertIn("FORBIDDEN_BUILTIN", rules)

    def test_dunder_manipulation_blocked(self):
        code = "x = ().__class__.__bases__[0].__subclasses__()\n"
        report = self.guardian.audit_source(code, "plugins/escape.py")
        self.assertFalse(report.approved)
        rules = [v.rule for v in report.violations]
        self.assertIn("DUNDER_MANIPULATION", rules)


if __name__ == "__main__":
    unittest.main()
