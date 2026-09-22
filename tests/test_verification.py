from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modfactory.scanner import scan_repository
from modfactory.slices import build_migration_slices
from modfactory.verification import (
    build_differential_verification,
    build_verification_contract,
    provision_verification_environment,
    validate_verification_contract,
    write_verification,
)


def _add_baseline(
    root: Path,
    test_body: str = "import unittest\n\nclass T(unittest.TestCase):\n    def test_x(self): self.assertTrue(True)\n",
) -> None:
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


class DifferentialFindingIdentityTests(unittest.TestCase):
    def test_large_file_line_count_change_is_not_a_new_finding_when_severity_is_stable(self):
        from modfactory.models import Finding
        from modfactory.verification import _finding_key

        before = Finding(
            category="maintainability", severity="high", path="big.tsx",
            message="Large source file (1217 lines)", evidence="", remediation="", score=8,
        )
        after = Finding(
            category="maintainability", severity="high", path="big.tsx",
            message="Large source file (1218 lines)", evidence="", remediation="", score=8,
        )
        escalated = Finding(
            category="maintainability", severity="high", path="big.tsx",
            message="Large source file (1201 lines)", evidence="", remediation="", score=8,
        )
        medium = Finding(
            category="maintainability", severity="medium", path="big.tsx",
            message="Large source file (1199 lines)", evidence="", remediation="", score=4,
        )

        self.assertEqual(_finding_key(before), _finding_key(after))
        self.assertNotEqual(_finding_key(medium), _finding_key(escalated))


class VerificationContractTests(unittest.TestCase):
    def test_contract_freezes_test_build_and_typecheck_commands(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "src").mkdir()
            (root / "src" / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
            (root / "test").mkdir()
            (root / "test" / "index.test.js").write_text("module.exports = true\n", encoding="utf-8")
            (root / "package.json").write_text(
                '{"scripts":{"test":"node test/index.test.js","build":"node -c src/index.js","typecheck":"node -c src/index.js"},"dependencies":{}}\n',
                encoding="utf-8",
            )
            (root / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text(
                "name: ci\njobs:\n  test:\n    steps:\n"
                "      - run: npm test\n"
                "      - run: npm run build\n"
                "      - run: npm run typecheck\n",
                encoding="utf-8",
            )

            snapshot = scan_repository(root)
            contract = build_verification_contract(root, snapshot)

            kinds = {item["kind"] for item in contract["commands"]}
            commands = {item["command"] for item in contract["commands"]}
            self.assertIn("test", kinds)
            self.assertIn("build", kinds)
            self.assertIn("lint", kinds)
            self.assertIn("npm test", commands)
            self.assertIn("npm run build", commands)
            self.assertIn("npm run typecheck", commands)
            self.assertEqual(contract["environment_model"]["baseline_target_isolation"], "shared-host")
            self.assertFalse(contract["environment_model"]["deployment_evidence"])
            dependency_paths = {item["path"] for item in contract["dependency_inputs"]}
            self.assertIn("package.json", dependency_paths)
            self.assertIn("package-lock.json", dependency_paths)
            valid, errors = validate_verification_contract(contract)
            self.assertTrue(valid, errors)

    def test_isolated_contract_declares_python_venv_strategy(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_app.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n    def test_x(self): self.assertTrue(True)\n",
                encoding="utf-8",
            )
            snapshot = scan_repository(root)
            contract = build_verification_contract(
                root,
                snapshot,
                isolated_dependencies=True,
            )

            model = contract["environment_model"]
            self.assertTrue(model["separate_dependency_environments"])
            self.assertTrue(model["strategy"]["supported"])
            self.assertEqual(model["strategy"]["steps"][0]["kind"], "python-venv")

    def test_contract_hash_detects_tampering(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_app.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n    def test_x(self): self.assertTrue(True)\n",
                encoding="utf-8",
            )
            snapshot = scan_repository(root)
            contract = build_verification_contract(root, snapshot)
            self.assertTrue(contract["commands"])
            contract["commands"][0]["command"] = "python -c pass"

            valid, errors = validate_verification_contract(contract)

            self.assertFalse(valid)
            self.assertIn("contract-sha256-mismatch", errors)


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

            self.assertEqual(result["status"], "REVIEW", result)
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

            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["verification_level"], "contract-shared-host")
            self.assertEqual(result["reason"], "verification-contract-pass-shared-host")
            self.assertTrue(result["project_tests"]["executed"])
            self.assertTrue(result["project_checks"]["executed"])
            self.assertFalse(result["deployment_admissible"])
            contract = result["verification_contract"]
            self.assertEqual(len(contract["contract_sha256"]), 64)
            self.assertEqual(
                [item["command"] for item in result["project_checks"]["before"]],
                [item["command"] for item in result["project_checks"]["after"]],
            )

    def test_opt_in_isolated_dependency_environments_are_distinct(self):
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
                provision_environments=True,
            )

            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(
                result["reason"],
                "verification-contract-pass-isolated-dependencies",
            )
            self.assertEqual(
                result["verification_level"],
                "contract-isolated-dependencies",
            )
            self.assertFalse(result["deployment_admissible"])
            before = result["environment_evidence"]["before"]
            after = result["environment_evidence"]["after"]
            self.assertEqual(before["status"], "PASS")
            self.assertEqual(after["status"], "PASS")
            self.assertNotEqual(
                before["runtime"]["virtual_env"],
                after["runtime"]["virtual_env"],
            )
            self.assertIn(".modfactory-env", before["runtime"]["virtual_env"])
            self.assertIn(".modfactory-env", after["runtime"]["virtual_env"])

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

            self.assertEqual(result["status"], "BLOCKED", result)
            self.assertEqual(result["reason"], "baseline-verification-contract-failed")

    def test_shell_metacharacter_test_command_is_blocked(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text(
                "from collections import MutableMapping\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text("", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_app.py").write_text(
                "import unittest\n\nclass T(unittest.TestCase):\n    def test_x(self): self.assertTrue(True)\n",
                encoding="utf-8",
            )
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

            self.assertEqual(result["status"], "BLOCKED", result)
            self.assertEqual(result["reason"], "baseline-verification-contract-failed")
            self.assertEqual(result["project_tests"]["before"][0]["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
