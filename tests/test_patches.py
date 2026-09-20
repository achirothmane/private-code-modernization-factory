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
    def test_deterministic_transform_is_blocked_without_baseline_tests_and_ci(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text(
                "from collections import MutableMapping\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text("", encoding="utf-8")

            snap = scan_repository(root)
            target_slice = next(
                item for item in build_migration_slices(snap)
                if item.get("recipe", {}).get("id") == "python-collections-abc"
            )
            proposal = build_patch_proposal(root, snap, str(target_slice["id"]))

            self.assertEqual(proposal["status"], "BLOCKED")
            self.assertEqual(proposal["reason"], "baseline-tests-missing")
            self.assertEqual(proposal["diff"], "")

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


    def _react_repo(self, root: Path, source: str, name: str = "index.tsx") -> tuple[object, dict]:
        (root / "src").mkdir()
        (root / "src" / name).write_text(source, encoding="utf-8")
        (root / "src" / "index.test.js").write_text("module.exports = true\n", encoding="utf-8")
        (root / "package.json").write_text(
            '{"scripts":{"test":"node src/index.test.js"},"dependencies":{"react":"^17.0.2","react-dom":"^17.0.2"}}\n',
            encoding="utf-8",
        )
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "workflows" / "ci.yml").write_text(
            "name: ci\njobs:\n  test:\n    steps:\n      - run: npm test\n",
            encoding="utf-8",
        )
        snap = scan_repository(root, targets={"react-dom": "18"})
        target_slice = next(
            item for item in build_migration_slices(snap)
            if item.get("recipe", {}).get("id") == "reactdom-render-to-createroot"
        )
        return snap, target_slice

    def test_react_get_element_by_id_becomes_deterministic_create_root(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            original = (
                "import ReactDOM from 'react-dom'\n"
                "ReactDOM.render(<App />, document.getElementById('root'))\n"
            )
            snap, target_slice = self._react_repo(root, original)
            proposal = build_patch_proposal(root, snap, str(target_slice["id"]))

            self.assertEqual(proposal["status"], "PROPOSED", proposal)
            self.assertIn("import { createRoot } from 'react-dom/client'", proposal["diff"])
            self.assertIn("createRoot(document.getElementById('root')!).render(<App />)", proposal["diff"])
            self.assertNotIn("+ReactDOM.render", proposal["diff"])
            self.assertEqual((root / "src" / "index.tsx").read_text(encoding="utf-8"), original)

    def test_react_append_child_container_is_one_shot_root(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            source = (
                "import ReactDOM from 'react-dom'\n"
                "const host = document.createElement('div')\n"
                "const child = document.createElement('div')\n"
                "ReactDOM.render(<Button />, host.appendChild(child))\n"
            )
            snap, target_slice = self._react_repo(root, source)
            proposal = build_patch_proposal(root, snap, str(target_slice["id"]))

            self.assertEqual(proposal["status"], "PROPOSED", proposal)
            self.assertIn("createRoot(host.appendChild(child)).render(<Button />)", proposal["diff"])

    def test_react_reused_named_container_creates_one_persistent_root(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            source = (
                "import ReactDOM from 'react-dom'\n"
                "const tooltipContainer = document.createElement('div')\n"
                "tooltipContainer.className = 'tip'\n"
                "function renderTip() {\n"
                "  ReactDOM.render(<Tip />, tooltipContainer)\n"
                "}\n"
            )
            snap, target_slice = self._react_repo(root, source)
            proposal = build_patch_proposal(root, snap, str(target_slice["id"]))

            self.assertEqual(proposal["status"], "PROPOSED", proposal)
            self.assertIn("const tooltipContainerRoot = createRoot(tooltipContainer)", proposal["diff"])
            self.assertIn("tooltipContainerRoot.render(<Tip />)", proposal["diff"])
            self.assertEqual(proposal["diff"].count("tooltipContainerRoot = createRoot"), 1)

    def test_react_unknown_container_lifetime_is_blocked(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            source = (
                "import ReactDOM from 'react-dom'\n"
                "function mount(container: HTMLElement) {\n"
                "  ReactDOM.render(<App />, container)\n"
                "}\n"
            )
            snap, target_slice = self._react_repo(root, source)
            proposal = build_patch_proposal(root, snap, str(target_slice["id"]))

            self.assertEqual(proposal["status"], "BLOCKED")
            self.assertEqual(proposal["reason"], "transform-blocked")
            self.assertIn("supported document.createElement", proposal["detail"])

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
