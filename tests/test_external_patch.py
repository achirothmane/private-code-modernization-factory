from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modfactory.external_patch import verify_external_patch, write_external_patch_verification


def _repo(root: Path, *, test_asserts_value: bool = False) -> None:
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "requirements.txt").write_text("", encoding="utf-8")
    (root / "tests").mkdir()
    if test_asserts_value:
        body = (
            "import unittest\n"
            "import app\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_value(self): self.assertEqual(app.VALUE, 1)\n"
        )
    else:
        body = (
            "import unittest\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_x(self): self.assertTrue(True)\n"
        )
    (root / "tests" / "test_app.py").write_text(body, encoding="utf-8")
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\njobs:\n  test:\n    steps:\n"
        "      - run: python -m unittest discover -s tests -v\n",
        encoding="utf-8",
    )


def _write_diff(root: Path, patch: Path, changes: dict[str, str]) -> str:
    chunks: list[str] = []
    for rel, after in changes.items():
        before = (root / rel).read_text(encoding="utf-8")
        chunks.extend(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        ))
    text = "".join(chunks)
    patch.write_text(text, encoding="utf-8")
    return text


class ExternalPatchVerificationTests(unittest.TestCase):
    def test_external_patch_is_hashed_and_reviewed_without_touching_original(self):
        with TemporaryDirectory() as td, TemporaryDirectory() as out:
            root = Path(td)
            _repo(root)
            patch = root.parent / f"{root.name}-safe.patch"
            diff = _write_diff(
                root,
                patch,
                {"app.py": "# modernization patch\nVALUE = 1\n"},
            )
            original = (root / "app.py").read_text(encoding="utf-8")

            result = verify_external_patch(
                root,
                patch,
                producer="codex",
            )

            self.assertEqual(result["status"], "REVIEW", result)
            self.assertEqual(result["reason"], "static-pass-project-contract-not-executed")
            self.assertEqual(result["producer"], "codex")
            self.assertEqual(
                result["patch_artifact"]["sha256"],
                hashlib.sha256(diff.encode("utf-8")).hexdigest(),
            )
            self.assertEqual(result["patch_artifact"]["changed_files"], ["app.py"])
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), original)
            self.assertEqual(len(result["baseline_files"][0]["sha256"]), 64)

            json_path, md_path = write_external_patch_verification(result, out)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

    def test_external_patch_passes_frozen_contract_when_before_and_after_are_green(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _repo(root)
            patch = root.parent / f"{root.name}-pass.patch"
            _write_diff(
                root,
                patch,
                {"app.py": "# harmless modernization metadata\nVALUE = 1\n"},
            )

            result = verify_external_patch(
                root,
                patch,
                producer="openrewrite",
                allow_project_code=True,
                timeout_seconds=30,
            )

            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["reason"], "external-patch-pass-shared-host")
            self.assertEqual(result["verification_level"], "external-patch-shared-host")
            self.assertTrue(result["project_checks"]["executed"])
            self.assertFalse(result["deployment_admissible"])
            self.assertEqual(
                [item["command"] for item in result["project_checks"]["before"]],
                [item["command"] for item in result["project_checks"]["after"]],
            )

    def test_external_patch_regression_fails_against_baseline_contract(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, test_asserts_value=True)
            patch = root.parent / f"{root.name}-regression.patch"
            _write_diff(root, patch, {"app.py": "VALUE = 2\n"})

            result = verify_external_patch(
                root,
                patch,
                producer="copilot",
                allow_project_code=True,
                timeout_seconds=30,
            )

            self.assertEqual(result["status"], "FAIL", result)
            self.assertEqual(result["reason"], "regression-after-external-patch")
            self.assertTrue(result["project_tests"]["before"])
            self.assertEqual(result["project_tests"]["before"][0]["status"], "PASS")
            self.assertEqual(result["project_tests"]["after"][0]["status"], "FAIL")

    def test_external_behavior_contract_catches_untested_regression(self):
        with TemporaryDirectory() as td, TemporaryDirectory() as evidence_td:
            root = Path(td)
            evidence_root = Path(evidence_td)
            _repo(root, test_asserts_value=False)
            patch = evidence_root / "regression.patch"
            _write_diff(root, patch, {"app.py": "VALUE = 2\n"})

            probe = evidence_root / "probe.py"
            probe.write_text(
                "import os, sys\n"
                "sys.path.insert(0, os.getcwd())\n"
                "import app\n"
                "assert app.VALUE == 1, app.VALUE\n",
                encoding="utf-8",
            )
            contract = evidence_root / "behavior.json"
            contract.write_text(
                json.dumps({
                    "schema_version": 1,
                    "commands": [{
                        "id": "value-remains-one",
                        "command": f"python {probe}",
                    }],
                }),
                encoding="utf-8",
            )

            result = verify_external_patch(
                root,
                patch,
                producer="external-tool",
                behavior_contract=contract,
                allow_project_code=True,
                timeout_seconds=30,
            )

            self.assertEqual(result["status"], "FAIL", result)
            self.assertEqual(result["reason"], "behavior-contract-regression")
            self.assertEqual(result["verification_level"], "behavior-contract")
            self.assertTrue(result["behavior_contract"]["executed"])
            self.assertEqual(
                result["behavior_contract"]["before"][0]["status"],
                "PASS",
            )
            self.assertEqual(
                result["behavior_contract"]["after"][0]["status"],
                "FAIL",
            )
            self.assertEqual(
                result["behavior_contract"]["evidence"]["case_ids"],
                ["value-remains-one"],
            )

    def test_behavior_contract_must_be_external_to_repository(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _repo(root)
            patch = root.parent / f"{root.name}-patch.diff"
            _write_diff(root, patch, {"app.py": "# safe\nVALUE = 1\n"})
            contract = root / "behavior.json"
            contract.write_text(
                json.dumps({
                    "schema_version": 1,
                    "commands": [{
                        "id": "noop",
                        "command": "python -V",
                    }],
                }),
                encoding="utf-8",
            )

            result = verify_external_patch(
                root,
                patch,
                behavior_contract=contract,
                allow_project_code=True,
            )

            self.assertEqual(result["status"], "BLOCKED", result)
            self.assertEqual(result["reason"], "behavior-contract-invalid")
            self.assertIn(
                "behavior-contract-must-be-external-to-repository",
                result["detail"],
            )

    def test_external_patch_cannot_modify_the_test_oracle(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, test_asserts_value=True)
            patch = root.parent / f"{root.name}-oracle.patch"
            _write_diff(
                root,
                patch,
                {
                    "app.py": "VALUE = 2\n",
                    "tests/test_app.py": (
                        "import unittest\n"
                        "import app\n\n"
                        "class T(unittest.TestCase):\n"
                        "    def test_value(self): self.assertTrue(True)\n"
                    ),
                },
            )

            result = verify_external_patch(
                root,
                patch,
                producer="claude",
                allow_project_code=True,
                timeout_seconds=30,
            )

            self.assertEqual(result["status"], "BLOCKED", result)
            self.assertEqual(result["reason"], "verification-oracle-modified")
            reasons = {item["reason"] for item in result["oracle_violations"]}
            self.assertIn("test-oracle-file-modified", reasons)
            self.assertFalse(result["project_checks"]["executed"])


if __name__ == "__main__":
    unittest.main()
