from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modfactory.patches import build_patch_proposal, validate_proposal_scope, write_patch_proposal
from modfactory.scanner import scan_repository
from modfactory.slices import build_migration_slices


def _add_baseline(root: Path) -> None:
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_app.py").write_text("def test_x(): assert True\n", encoding="utf-8")
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\njobs:\n  test:\n    steps:\n      - run: python -m unittest discover -s tests -v\n",
        encoding="utf-8",
    )


class PatchProposalTests(unittest.TestCase):
    def test_collections_recipe_produces_single_file_review_only_diff(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            original = "from collections import MutableMapping\n\nclass Config(MutableMapping):\n    pass\n"
            (root / "app.py").write_text(original, encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            _add_baseline(root)

            snap = scan_repository(root)
            target_slice = next(
                item for item in build_migration_slices(snap)
                if item.get("recipe", {}).get("id") == "python-collections-abc"
            )
            proposal = build_patch_proposal(root, snap, str(target_slice["id"]))

            self.assertEqual(proposal["status"], "PROPOSED")
            self.assertEqual(proposal["changed_files"], ["app.py"])
            self.assertEqual(proposal["allowed_files"], ["app.py"])
            self.assertFalse(proposal["applies_changes"])
            self.assertFalse(proposal["creates_commits"])
            self.assertFalse(proposal["auto_merges"])
            self.assertIn("from collections.abc import MutableMapping", proposal["diff"])
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), original)

    def test_semantic_imp_recipe_is_blocked_until_transform_exists(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text(
                "import imp\n\ndef load(name):\n    return imp.load_source(name, name + '.py')\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text("", encoding="utf-8")
            _add_baseline(root)

            snap = scan_repository(root)
            target_slice = next(
                item for item in build_migration_slices(snap)
                if item.get("recipe", {}).get("id") == "python-imp-to-importlib"
            )
            proposal = build_patch_proposal(root, snap, str(target_slice["id"]))

            self.assertEqual(proposal["status"], "BLOCKED")
            self.assertEqual(proposal["reason"], "deterministic-transform-not-implemented")
            self.assertEqual(proposal["diff"], "")

    def test_diff_budget_blocks_large_proposal(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            body = "\n".join(
                f"class C{i}(collections.MutableMapping): pass"
                for i in range(10)
            )
            (root / "app.py").write_text("import collections\n" + body + "\n", encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            _add_baseline(root)

            snap = scan_repository(root)
            target_slice = next(
                item for item in build_migration_slices(snap)
                if item.get("recipe", {}).get("id") == "python-collections-abc"
            )
            proposal = build_patch_proposal(root, snap, str(target_slice["id"]), diff_budget=1)

            self.assertEqual(proposal["status"], "BLOCKED")
            self.assertEqual(proposal["reason"], "diff-budget-exceeded")
            self.assertGreater(proposal["changed_lines"], 1)
            self.assertEqual(proposal["diff"], "")

    def test_scope_validator_rejects_outside_file(self):
        ok, violations = validate_proposal_scope({
            "allowed_files": ["app.py"],
            "changed_files": ["app.py", "secrets.txt"],
        })
        self.assertFalse(ok)
        self.assertEqual(violations, ["secrets.txt"])

    def test_write_proposal_artifacts_does_not_apply_patch(self):
        with TemporaryDirectory() as td, TemporaryDirectory() as out:
            root = Path(td)
            original = "from collections import Mapping\n"
            (root / "app.py").write_text(original, encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            _add_baseline(root)

            snap = scan_repository(root)
            target_slice = next(
                item for item in build_migration_slices(snap)
                if item.get("recipe", {}).get("id") == "python-collections-abc"
            )
            proposal = build_patch_proposal(root, snap, str(target_slice["id"]))
            json_path, diff_path = write_patch_proposal(proposal, out)

            self.assertTrue(json_path.exists())
            self.assertTrue(diff_path.exists())
            self.assertIn("collections.abc", diff_path.read_text(encoding="utf-8"))
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
