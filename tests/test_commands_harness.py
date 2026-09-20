from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from modfactory.commands import discover_commands
from modfactory.harness import build_test_harness, render_baseline_script
from modfactory.report import write_report
from modfactory.scanner import scan_repository


class CommandDiscoveryTests(unittest.TestCase):
    def test_package_json_scripts_are_discovered_but_never_auto_executed(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.js").write_text("console.log('ok')\n", encoding="utf-8")
            (root / "package.json").write_text(json.dumps({
                "scripts": {
                    "test": "node --test",
                    "build": "webpack",
                    "lint": "eslint .",
                }
            }), encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "app.test.js").write_text("console.log('test')\n", encoding="utf-8")

            snap = scan_repository(root)
            commands = discover_commands(root, snap)
            by_command = {item["command"]: item for item in commands}

            self.assertIn("npm test", by_command)
            self.assertIn("npm run build", by_command)
            self.assertIn("npm run lint", by_command)
            self.assertFalse(by_command["npm test"]["auto_execute"])
            self.assertEqual(by_command["npm test"]["execution_policy"], "manual-or-sandbox-only")

    def test_python_unittest_command_is_inferred_from_test_layout(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_app.py").write_text("def test_x(): assert True\n", encoding="utf-8")

            snap = scan_repository(root)
            commands = discover_commands(root, snap)
            self.assertTrue(any(item["command"] == "python -m unittest discover -s tests -v" for item in commands))


    def test_legacy_tox_doctest_baseline_is_discovered(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "module.py").write_text("VALUE = 1\\n", encoding="utf-8")
            (root / "setup.py").write_text("from distutils.core import setup\\n", encoding="utf-8")
            (root / "tox.ini").write_text(
                "[tox]\\nenvlist = py311\\n\\n[testenv]\\ncommands = python -m doctest -v README.rst\\n",
                encoding="utf-8",
            )
            (root / "README.rst").write_text("Example\\n=======\\n", encoding="utf-8")

            snap = scan_repository(root)
            commands = discover_commands(root, snap)
            discovered = {item["command"] for item in commands}
            self.assertIn("tox", discovered)
            self.assertIn("python -m doctest -v README.rst", discovered)
            self.assertIn("python setup.py build", discovered)


class HarnessTests(unittest.TestCase):
    def test_missing_python_tests_generate_static_syntax_harness_only(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text("print('legacy')\n", encoding="utf-8")
            (root / "requirements.txt").write_text("flask==1.0\n", encoding="utf-8")

            snap = scan_repository(root)
            commands = discover_commands(root, snap)
            harness = build_test_harness(snap, commands)
            script = render_baseline_script(harness)

            self.assertEqual(harness["status"], "generated-minimum")
            self.assertFalse(harness["auto_executes_project_code"])
            self.assertTrue(any(item["path"] == "python_syntax_check.py" for item in harness["generated_files"]))
            self.assertIn("does NOT execute build/test commands", script)
            self.assertNotIn("import app", script)

    def test_report_writes_harness_artifacts(self):
        with TemporaryDirectory() as td, TemporaryDirectory() as out:
            root = Path(td)
            (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")

            write_report(scan_repository(root), out)
            harness_dir = Path(out) / "harness"
            self.assertTrue((harness_dir / "harness.json").exists())
            self.assertTrue((harness_dir / "baseline.sh").exists())
            self.assertTrue((harness_dir / "python_syntax_check.py").exists())


if __name__ == "__main__":
    unittest.main()
