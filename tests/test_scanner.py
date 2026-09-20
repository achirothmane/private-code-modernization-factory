from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from modfactory.planner import build_plan
from modfactory.scanner import scan_repository
from modfactory.slices import build_migration_slices


class ScannerTests(unittest.TestCase):
    def test_missing_tests_and_ci_are_blockers(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text("import imp\nprint('legacy')\n", encoding="utf-8")
            (root / "requirements.txt").write_text("flask==1.0\n", encoding="utf-8")
            snap = scan_repository(root)
            messages = {f.message for f in snap.findings}
            self.assertIn("No automated test files detected", messages)
            self.assertIn("No GitHub Actions CI workflow detected", messages)
            self.assertTrue(any("imp module" in m for m in messages))
            self.assertGreaterEqual(snap.risk_score, 45)

    def test_tests_and_ci_reduce_risk(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_app.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
            snap = scan_repository(root)
            self.assertLess(snap.risk_score, 20)
            phases = [p["title"] for p in build_plan(snap)]
            self.assertIn("Validate the existing test safety net", phases)

    def test_python_detector_ignores_docstring_mentions(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text(
                '"""Copied from distutils.util. import imp is also mentioned here."""\nVALUE = 1\n',
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text("", encoding="utf-8")
            snap = scan_repository(root)
            legacy = [f.message for f in snap.findings if f.category == "legacy-api"]
            self.assertNotIn("distutils is removed from modern Python", legacy)
            self.assertNotIn("Python imp module is removed in Python 3.12+", legacy)

    def test_python_detector_uses_import_syntax_not_free_text(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text(
                "from distutils.core import setup\nfrom collections import MutableMapping\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text("", encoding="utf-8")
            snap = scan_repository(root)
            messages = {f.message for f in snap.findings}
            self.assertIn("distutils is removed from modern Python", messages)
            self.assertIn("Legacy collections ABC import pattern", messages)

    def test_npm_detector_only_counts_direct_package_json_dependencies(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
            (root / "package.json").write_text(
                json.dumps({
                    "devDependencies": {
                        "request": "^2.88.0",
                        "node-sass": "^9.0.0",
                    }
                }),
                encoding="utf-8",
            )
            (root / "package-lock.json").write_text(
                json.dumps({
                    "dependencies": {
                        "request": {"version": "2.88.0"},
                        "node-sass": {"version": "9.0.0"},
                    }
                }),
                encoding="utf-8",
            )
            snap = scan_repository(root)
            legacy = [f for f in snap.findings if f.category == "legacy-api"]
            self.assertEqual(sum(f.message == "request npm package is deprecated" for f in legacy), 1)
            self.assertEqual(sum(f.message == "node-sass is deprecated" for f in legacy), 1)
            self.assertTrue(all(f.path == "package.json" for f in legacy))

    def test_javax_detector_excludes_java_se_jcache_and_free_text(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "pom.xml").write_text(
                "<groupId>javax.cache</groupId>\n<!-- javax.persistence is text only -->\n",
                encoding="utf-8",
            )
            (root / "Safe.java").write_text(
                "import javax.tools.JavaCompiler;\n"
                "import javax.naming.event.ObjectChangeListener;\n"
                "import javax.cache.configuration.MutableConfiguration;\n"
                'class Safe { String s = "javax.persistence.Entity"; }\n',
                encoding="utf-8",
            )
            (root / "pom.xml").write_text("<project></project>\n", encoding="utf-8")
            snap = scan_repository(root)
            messages = [f.message for f in snap.findings if f.category == "legacy-api"]
            self.assertNotIn("Javax namespace detected", messages)

    def test_javax_detector_keeps_known_jakarta_candidate_imports(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "App.java").write_text(
                "import javax.persistence.Entity;\nclass App {}\n",
                encoding="utf-8",
            )
            (root / "pom.xml").write_text("<project></project>\n", encoding="utf-8")
            snap = scan_repository(root)
            findings = [f for f in snap.findings if f.message == "Javax namespace detected"]
            self.assertEqual(len(findings), 1)
            self.assertIn("javax.persistence.Entity", findings[0].evidence)


class HistoryTests(unittest.TestCase):
    def test_git_history_identifies_single_owner_hotspot(self):
        import subprocess
        with TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "dev@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Dev"], check=True)
            (root / "requirements.txt").write_text("flask==1.0\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_app.py").write_text("def test_x(): assert True\n", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
            for i in range(6):
                (root / "app.py").write_text(f"VALUE = {i}\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(root), "add", "."], check=True)
                subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", f"change {i}"], check=True)
            snap = scan_repository(root)
            self.assertTrue(snap.history["available"])
            self.assertGreaterEqual(snap.history["commits_analyzed"], 6)
            self.assertTrue(any(f.category == "ownership" and f.path == "app.py" for f in snap.findings))


class ArchitectureTests(unittest.TestCase):
    def test_python_dependency_graph_detects_cycle_and_hub(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "pkg").mkdir()
            (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (root / "pkg" / "a.py").write_text("from pkg import b\n", encoding="utf-8")
            (root / "pkg" / "b.py").write_text("from pkg import a\n", encoding="utf-8")
            for name in ["c", "d", "e"]:
                (root / "pkg" / f"{name}.py").write_text("from pkg import a\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_pkg.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
            snap = scan_repository(root)
            self.assertGreaterEqual(snap.architecture["edge_count"], 5)
            self.assertTrue(any(set(cycle) == {"pkg/a.py", "pkg/b.py"} for cycle in snap.architecture["cycles"]))
            self.assertTrue(any(hub["path"] == "pkg/a.py" and hub["fan_in"] >= 4 for hub in snap.architecture["hubs"]))
            migration_slices = build_migration_slices(snap)
            self.assertTrue(any(item["kind"] == "architecture" and "cycle" in item["title"].lower() for item in migration_slices))
            self.assertTrue(any(item["kind"] == "architecture" and "hub" in item["title"].lower() for item in migration_slices))


if __name__ == "__main__":
    unittest.main()
