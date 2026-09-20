from pathlib import Path
from tempfile import TemporaryDirectory
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
