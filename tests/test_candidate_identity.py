from __future__ import annotations

import difflib
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import tempfile
import unittest
from unittest.mock import patch

from modfactory.external_patch import verify_external_patch
from modfactory.model_bench import _git_apply, inspect_unified_diff


def _init_git(root: Path) -> None:
    subprocess.run(
        ["git", "init", "-q"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _repo(root: Path, *, test_asserts_value: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "other.py").write_text("OTHER = 1\n", encoding="utf-8")
    (root / "requirements.txt").write_text("", encoding="utf-8")
    (root / "tests").mkdir()
    if test_asserts_value:
        body = (
            "import unittest\nimport app\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_value(self): self.assertEqual(app.VALUE, 1)\n"
        )
    else:
        body = (
            "import unittest\n\nclass T(unittest.TestCase):\n"
            "    def test_x(self): self.assertTrue(True)\n"
        )
    (root / "tests" / "test_app.py").write_text(body, encoding="utf-8")
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\njobs:\n  test:\n    steps:\n"
        "      - run: python -m unittest discover -s tests -v\n",
        encoding="utf-8",
    )


def _diff(root: Path, changes: dict[str, str]) -> str:
    chunks: list[str] = []
    for rel, after in changes.items():
        before = (root / rel).read_text(encoding="utf-8")
        chunks.extend(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        ))
    return "".join(chunks)


class CandidateIdentityRegressionTests(unittest.TestCase):
    def test_git_apply_changes_candidate_nested_under_parent_checkout(self):
        with TemporaryDirectory() as td:
            parent = Path(td)
            _init_git(parent)
            candidate = parent / "candidate"
            candidate.mkdir()
            target = candidate / "app.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            diff = (
                "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
                "-VALUE = 1\n+VALUE = 2\n"
            )

            ok, detail = _git_apply(candidate, diff, check_only=False)

            self.assertTrue(ok, detail)
            self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 2\n")

    def test_git_apply_ignores_inherited_git_directory_and_worktree(self):
        with TemporaryDirectory() as td:
            parent = Path(td)
            _init_git(parent)
            candidate = parent / "candidate"
            candidate.mkdir()
            target = candidate / "app.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            diff = (
                "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
                "-VALUE = 1\n+VALUE = 2\n"
            )

            with patch.dict(
                os.environ,
                {
                    "GIT_DIR": str(parent / ".git"),
                    "GIT_WORK_TREE": str(parent),
                    "GIT_INDEX_FILE": str(parent / ".git" / "index"),
                },
                clear=False,
            ):
                ok, detail = _git_apply(candidate, diff, check_only=False)

            self.assertTrue(ok, detail)
            self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 2\n")

    def test_nested_safe_patch_binds_actual_candidate_and_oracle_identity(self):
        with TemporaryDirectory() as td:
            parent = Path(td)
            _init_git(parent)
            root = parent / "source"
            _repo(root)
            patch_path = parent / "safe.patch"
            patch_path.write_text(
                _diff(root, {"app.py": "# metadata\nVALUE = 1\n"}),
                encoding="utf-8",
            )
            original = (root / "app.py").read_bytes()

            old_tempdir = tempfile.tempdir
            tempfile.tempdir = str(parent)
            try:
                result = verify_external_patch(root, patch_path)
            finally:
                tempfile.tempdir = old_tempdir

            self.assertEqual(result["status"], "REVIEW", result)
            identity = result["candidate_identity"]
            self.assertTrue(identity["candidate_differs_from_baseline"])
            self.assertTrue(identity["changed_files_match"])
            self.assertEqual(identity["actual_changed_files"], ["app.py"])
            self.assertNotEqual(
                identity["baseline_tree_sha256"],
                identity["candidate_tree_sha256"],
            )
            self.assertTrue(result["verification_oracle_identity"]["unchanged"])
            self.assertEqual((root / "app.py").read_bytes(), original)

    def test_nested_regression_patch_cannot_false_pass(self):
        with TemporaryDirectory() as td:
            parent = Path(td)
            _init_git(parent)
            root = parent / "source"
            _repo(root, test_asserts_value=True)
            patch_path = parent / "regression.patch"
            patch_path.write_text(
                _diff(root, {"app.py": "VALUE = 2\n"}),
                encoding="utf-8",
            )

            old_tempdir = tempfile.tempdir
            tempfile.tempdir = str(parent)
            try:
                result = verify_external_patch(
                    root,
                    patch_path,
                    allow_project_code=True,
                    timeout_seconds=30,
                )
            finally:
                tempfile.tempdir = old_tempdir

            self.assertEqual(result["status"], "FAIL", result)
            self.assertEqual(result["reason"], "regression-after-external-patch")
            self.assertEqual(result["candidate_identity"]["actual_changed_files"], ["app.py"])
            self.assertEqual(result["project_tests"]["before"][0]["status"], "PASS")
            self.assertEqual(result["project_tests"]["after"][0]["status"], "FAIL")

    def test_accidental_noop_patch_is_blocked_before_oracle_execution(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "source"
            _repo(root)
            patch_path = Path(td) / "noop.patch"
            patch_path.write_text(
                "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
                "-VALUE = 1\n+VALUE = 1\n",
                encoding="utf-8",
            )

            result = verify_external_patch(
                root,
                patch_path,
                allow_project_code=True,
                timeout_seconds=30,
            )

            self.assertEqual(result["status"], "BLOCKED", result)
            self.assertEqual(result["reason"], "patch-produced-no-candidate-change")
            self.assertTrue(result["candidate_identity"]["no_op"])
            self.assertFalse(result["project_checks"]["executed"])

    def test_partial_patch_is_rejected_without_touching_original(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "source"
            _repo(root)
            patch_path = Path(td) / "partial.patch"
            patch_path.write_text(
                "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
                "-VALUE = 1\n+VALUE = 2\n"
                "--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n"
                "-DOES_NOT_MATCH = 1\n+OTHER = 2\n",
                encoding="utf-8",
            )
            original_app = (root / "app.py").read_bytes()
            original_other = (root / "other.py").read_bytes()

            result = verify_external_patch(root, patch_path)

            self.assertEqual(result["status"], "FAIL", result)
            self.assertEqual(result["reason"], "patch-does-not-apply-cleanly")
            self.assertEqual((root / "app.py").read_bytes(), original_app)
            self.assertEqual((root / "other.py").read_bytes(), original_other)

    def test_unexpected_candidate_path_change_blocks_verification(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "source"
            _repo(root)
            patch_path = Path(td) / "safe.patch"
            patch_path.write_text(_diff(root, {"app.py": "VALUE = 2\n"}), encoding="utf-8")
            from modfactory.model_bench import _git_apply as real_git_apply

            def contaminated_apply(candidate_root: Path, diff: str, *, check_only: bool):
                ok, detail = real_git_apply(candidate_root, diff, check_only=check_only)
                if ok and not check_only:
                    (candidate_root / "other.py").write_text("OTHER = 999\n", encoding="utf-8")
                return ok, detail

            with patch("modfactory.external_patch._git_apply", side_effect=contaminated_apply):
                result = verify_external_patch(root, patch_path)

            self.assertEqual(result["status"], "BLOCKED", result)
            self.assertEqual(result["reason"], "candidate-identity-mismatch")
            self.assertEqual(
                result["candidate_identity"]["actual_changed_files"],
                ["app.py", "other.py"],
            )
            self.assertFalse(result["project_checks"]["executed"])

    def test_rename_and_delete_are_explicitly_unsupported(self):
        renamed = inspect_unified_diff(
            "diff --git a/app.py b/app2.py\n"
            "similarity index 100%\nrename from app.py\nrename to app2.py\n"
        )
        deleted = inspect_unified_diff(
            "diff --git a/app.py b/app.py\ndeleted file mode 100644\n"
            "--- a/app.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-VALUE = 1\n"
        )

        self.assertFalse(renamed["valid"])
        self.assertFalse(deleted["valid"])
        self.assertIn("unsupported-diff-operation", renamed["errors"])
        self.assertIn("unsupported-diff-operation", deleted["errors"])


if __name__ == "__main__":
    unittest.main()
