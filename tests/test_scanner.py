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

    def test_python_311_target_suppresses_python312_removed_api_signal(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text("import imp\n", encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            snap = scan_repository(root, targets={"python": "3.11"})
            self.assertFalse(any("imp module" in f.message for f in snap.findings))

            targeted = scan_repository(root, targets={"python": "3.12"})
            self.assertTrue(any("imp module" in f.message for f in targeted.findings))

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

    def test_npm_detector_only_counts_direct_package_json_dependencies_with_usage(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.js").write_text(
                "const request = require('request');\nconst sass = require('node-sass');\n",
                encoding="utf-8",
            )
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

    def test_unused_deprecated_npm_dependency_does_not_escalate_to_semantic_migration(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
            (root / "package.json").write_text(
                json.dumps({"devDependencies": {"request": "^2.88.0"}}),
                encoding="utf-8",
            )
            snap = scan_repository(root)
            legacy = [f for f in snap.findings if f.category == "legacy-api"]
            hygiene = [f for f in snap.findings if f.category == "dependency-hygiene"]
            self.assertFalse(any(f.message == "request npm package is deprecated" for f in legacy))
            self.assertEqual(len(hygiene), 1)
            self.assertIn("no observed source usage", hygiene[0].message)

    def test_reactdom_render_is_not_escalated_for_react_17(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "ui" / "src").mkdir(parents=True)
            (root / "ui" / "package.json").write_text(
                json.dumps({"dependencies": {"react": "^17.0.2", "react-dom": "^17.0.2"}}),
                encoding="utf-8",
            )
            (root / "ui" / "src" / "index.tsx").write_text(
                "import ReactDOM from 'react-dom';\nReactDOM.render(<App />, document.getElementById('root'));\n",
                encoding="utf-8",
            )
            snap = scan_repository(root)
            self.assertFalse(any(f.message == "Legacy React render API detected" for f in snap.findings))

    def test_react17_render_escalates_when_explicit_target_is_react18(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "ui" / "src").mkdir(parents=True)
            (root / "ui" / "package.json").write_text(
                json.dumps({"dependencies": {"react": "^17.0.2", "react-dom": "^17.0.2"}}),
                encoding="utf-8",
            )
            (root / "ui" / "src" / "index.tsx").write_text(
                "import ReactDOM from 'react-dom';\nReactDOM.render(<App />, document.getElementById('root'));\n",
                encoding="utf-8",
            )
            snap = scan_repository(root, targets={"react-dom": "18"})
            findings = [f for f in snap.findings if f.message == "Legacy React render API detected"]
            self.assertEqual(len(findings), 1)
            self.assertIn("explicit target react-dom=18", findings[0].evidence)
            self.assertEqual(snap.target_profile, {"react-dom": "18"})

    def test_reactdom_render_is_escalated_when_react_dom_is_18_plus(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "ui" / "src").mkdir(parents=True)
            (root / "ui" / "package.json").write_text(
                json.dumps({"dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0"}}),
                encoding="utf-8",
            )
            (root / "ui" / "src" / "index.tsx").write_text(
                "import ReactDOM from 'react-dom';\nReactDOM.render(<App />, document.getElementById('root'));\n",
                encoding="utf-8",
            )
            snap = scan_repository(root)
            findings = [f for f in snap.findings if f.message == "Legacy React render API detected"]
            self.assertEqual(len(findings), 1)
            self.assertIn("react-dom=^18.2.0", findings[0].evidence)

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

    def test_javax_detector_requires_spring_boot_3_context(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "App.java").write_text(
                "import javax.persistence.Entity;\nclass App {}\n",
                encoding="utf-8",
            )
            (root / "pom.xml").write_text(
                "<project><properties><spring-boot.version>2.7.18</spring-boot.version></properties></project>\n",
                encoding="utf-8",
            )
            snap = scan_repository(root)
            self.assertFalse(any(f.message == "Javax namespace detected" for f in snap.findings))

            targeted = scan_repository(root, targets={"spring-boot": "3.3"})
            findings = [f for f in targeted.findings if f.message == "Javax namespace detected"]
            self.assertEqual(len(findings), 1)
            self.assertIn("javax.persistence.Entity", findings[0].evidence)
            self.assertIn("explicit target spring-boot=3.3", findings[0].evidence)

    def test_javax_detector_infers_current_spring_boot_3(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "src").mkdir()
            (root / "src" / "App.java").write_text(
                "import javax.persistence.Entity;\nclass App {}\n",
                encoding="utf-8",
            )
            (root / "pom.xml").write_text(
                "<project><properties><spring-boot.version>3.4.2</spring-boot.version></properties></project>\n",
                encoding="utf-8",
            )
            snap = scan_repository(root)
            findings = [f for f in snap.findings if f.message == "Javax namespace detected"]
            self.assertEqual(len(findings), 1)
            self.assertIn("Spring Boot 3.4.2", findings[0].evidence)


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
