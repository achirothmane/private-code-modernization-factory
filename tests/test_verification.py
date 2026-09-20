from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modfactory.scanner import scan_repository
from modfactory.slices import build_migration_slices
from modfactory.verification import build_differential_verification, write_verification


def _add_baseline(root: Path, test_body: str = "def test_x(): assert True\n") -> None:
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_app.py").write_text(test_body, encoding="utf-8")
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\njobs:\n  test:\n    steps:\n      - run: python -m unittest discover -s tests -v\n",
        encoding="utf-8",
    )


def _slice_id(root: Path) -> tuple[object, str]:
    snap = scan_repository(root)
    item = next(
        row for row in build_migration_slices(snap)
        if row.get("recipe", {}).get("id") == "python-collections-abc"
    )
    return snap, str(item["id"])


class DifferentialVerificationTests(unittest.TestCase):
    def test_static_verification_removes_target_finding_without_touching_original(self):
        with TemporaryDirectory() as td, TemporaryDirectory() as out:
            root = Path(td)
            original = "from collections import MutableMapping\n\nclass Config(MutableMapping):\n    pass\n"
            (root / "app.py").write_text(original, encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            _add_baseline(root)
            snap, slice_id = _slice_id(root)

            result = build_differential_verification(root, snap, slice_id)

            self.assertEqual(result["status"], "REVIEW")
            self.assertEqual(result["reason"], "static-pass-project-tests-not-executed")
            self.assertTrue(result["static_checks"]["target_finding_removed_after"])
            self.assertFalse(result["static_checks"]["new_findings"])
            self.assertFalse(result["deployment_admissible"])
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), original)

            json_path, md_path = write_verification(result, out)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

    def test_opt_in_project_tests_produce_pass_when_before_and_after_are_green(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text(
                "from collections import MutableMapping\n\nVALUE = 1\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text("", encoding="utf-8")
            _add_baseline(root)
            snap, slice_id = _slice_id(root)

            result = build_differential_verification(
                root,
                snap,
                slice_id,
                allow_project_code=True,
                timeout_seconds=30,
            )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["verification_level"], "tests")
            self.assertTrue(result["project_tests"]["executed"])
            self.assertTrue(result["deployment_admissible"])

    def test_failing_before_baseline_blocks_attribution_to_patch(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text(
                "from collections import MutableMapping\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text("", encoding="utf-8")
            _add_baseline(
                root,
                "import unittest\n\nclass T(unittest.TestCase):\n    def test_fail(self): self.fail('baseline')\n",
            )
            snap, slice_id = _slice_id(root)

            result = build_differential_verification(
                root,
                snap,
                slice_id,
                allow_project_code=True,
                timeout_seconds=30,
            )

            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["reason"], "baseline-failed-before")

    def test_shell_metacharacter_test_command_is_blocked(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text(
                "from collections import MutableMapping\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text("", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_app.py").write_text("def test_x(): assert True\n", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text(
                "name: ci\njobs:\n  test:\n    steps:\n      - run: python -m unittest discover -s tests -v && echo unsafe\n",
                encoding="utf-8",
            )
            snap, slice_id = _slice_id(root)

            result = build_differential_verification(
                root,
                snap,
                slice_id,
                allow_project_code=True,
                timeout_seconds=30,
            )

            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["reason"], "baseline-failed-before")
            self.assertEqual(result["project_tests"]["before"][0]["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
