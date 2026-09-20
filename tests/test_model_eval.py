from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from modfactory.model_eval import build_model_evaluation_plan, write_model_evaluation_plan
from modfactory.scanner import scan_repository


class ModelEvaluationPlanTests(unittest.TestCase):
    def _react17_repo(self, root: Path, *, with_tests: bool = True, with_ci: bool = True) -> None:
        (root / "src").mkdir()
        (root / "src" / "index.tsx").write_text(
            "import ReactDOM from 'react-dom';\n"
            "ReactDOM.render(<App />, document.getElementById('root'));\n",
            encoding="utf-8",
        )
        (root / "package.json").write_text(
            json.dumps({
                "scripts": {"test": "node src/index.test.js"},
                "dependencies": {"react": "^17.0.2", "react-dom": "^17.0.2"},
            }),
            encoding="utf-8",
        )
        if with_tests:
            (root / "src" / "index.test.js").write_text("module.exports = true\n", encoding="utf-8")
        if with_ci:
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text(
                "name: ci\njobs:\n  test:\n    steps:\n      - run: npm test\n",
                encoding="utf-8",
            )

    def test_explicit_react18_target_is_consumed_by_deterministic_transform_before_model_eval(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            self._react17_repo(root)
            snapshot = scan_repository(root, targets={"react-dom": "18"})

            plan = build_model_evaluation_plan(root, snapshot)

            self.assertEqual(plan["eligible_tasks"], 0, plan)
            self.assertEqual(plan["blocked_tasks"], 0)
            self.assertEqual(plan["tasks"], [])
            self.assertEqual(plan["compute_policy"]["next_gate"], "NO_ELIGIBLE_SEMANTIC_TASK")
            self.assertFalse(plan["compute_policy"]["invoke_model"])
            self.assertFalse(plan["compute_policy"]["rent_b300"])

    def test_missing_verification_prerequisites_blocks_model_task(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            self._react17_repo(root, with_tests=False, with_ci=False)
            snapshot = scan_repository(root, targets={"react-dom": "18"})

            plan = build_model_evaluation_plan(root, snapshot)

            self.assertEqual(plan["eligible_tasks"], 0)
            self.assertEqual(plan["blocked_tasks"], 1)
            self.assertEqual(plan["blocked"][0]["reason"], "baseline-tests-missing")
            self.assertEqual(plan["compute_policy"]["next_gate"], "NO_ELIGIBLE_SEMANTIC_TASK")

    def test_plan_artifacts_are_reproducible_and_do_not_invoke_models(self):
        with TemporaryDirectory() as td, TemporaryDirectory() as out:
            root = Path(td)
            self._react17_repo(root)
            snapshot = scan_repository(root, targets={"react-dom": "18"})
            plan = build_model_evaluation_plan(root, snapshot)

            json_path, jsonl_path, md_path = write_model_evaluation_plan(plan, out)

            self.assertTrue(json_path.exists())
            self.assertTrue(jsonl_path.exists())
            self.assertTrue(md_path.exists())
            self.assertEqual(jsonl_path.read_text(encoding="utf-8"), "")
            self.assertIn("No model was invoked", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
