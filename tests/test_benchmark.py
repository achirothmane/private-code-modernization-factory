from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from modfactory.benchmark import (
    benchmark_corpus,
    benchmark_repository,
    classify_escalation,
    write_benchmark,
)


def _baseline(root: Path, command: str = "python -m unittest discover -s tests -v") -> None:
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_app.py").write_text(
        "import unittest\n\nclass T(unittest.TestCase):\n    def test_x(self): self.assertTrue(True)\n",
        encoding="utf-8",
    )
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(
        f"name: ci\njobs:\n  test:\n    steps:\n      - run: {command}\n",
        encoding="utf-8",
    )


class BenchmarkTests(unittest.TestCase):
    def test_deterministic_repo_is_measured_without_llm_escalation(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text(
                "from collections import MutableMapping\n\nclass C(MutableMapping):\n    pass\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text("", encoding="utf-8")
            _baseline(root)

            result = benchmark_repository(root, name="deterministic")

            self.assertEqual(result["patch_proposals"], 1, result)
            self.assertEqual(result["semantic_escalations"], 0)
            self.assertEqual(result["escalation"]["tier"], "DETERMINISTIC")
            self.assertFalse(result["escalation"]["b300_rental_recommended"])

    def test_medium_confidence_recipe_becomes_semantic_review_candidate(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.js").write_text("const sass = require(\'node-sass\');\nmodule.exports = sass;\n", encoding="utf-8")
            (root / "index.test.js").write_text("module.exports = true\n", encoding="utf-8")
            (root / "package.json").write_text(
                json.dumps({
                    "scripts": {"test": "node index.test.js"},
                    "dependencies": {"node-sass": "9.0.0"},
                }),
                encoding="utf-8",
            )
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text(
                "name: ci\njobs:\n  test:\n    steps:\n      - run: npm test\n",
                encoding="utf-8",
            )

            result = benchmark_repository(root, name="semantic")

            self.assertEqual(result["patch_proposals"], 0)
            self.assertGreaterEqual(result["semantic_escalations"], 1)
            self.assertEqual(result["escalation"]["tier"], "SEMANTIC_REVIEW_CANDIDATE")
            self.assertFalse(result["escalation"]["b300_rental_recommended"])

    def test_manifest_target_turns_react17_into_explicit_react18_migration(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "src").mkdir()
            (root / "src" / "index.js").write_text(
                "import ReactDOM from 'react-dom';\nReactDOM.render(<App />, document.getElementById('root'));\n",
                encoding="utf-8",
            )
            (root / "src" / "index.test.js").write_text("module.exports = true\n", encoding="utf-8")
            (root / "package.json").write_text(
                json.dumps({
                    "scripts": {"test": "node src/index.test.js"},
                    "dependencies": {"react": "^17.0.2", "react-dom": "^17.0.2"},
                }),
                encoding="utf-8",
            )
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text(
                "name: ci\njobs:\n  test:\n    steps:\n      - run: npm test\n",
                encoding="utf-8",
            )

            no_target = benchmark_repository(root, name="react17")
            self.assertEqual(no_target["semantic_escalations"], 0)

            targeted = benchmark_repository(
                root,
                name="react18-target",
                targets={"react-dom": "18"},
            )
            self.assertGreaterEqual(targeted["semantic_escalations"], 1)
            self.assertEqual(targeted["target_profile"], {"react-dom": "18"})
            self.assertEqual(targeted["escalation"]["tier"], "SEMANTIC_REVIEW_CANDIDATE")

    def test_architecture_only_pressure_does_not_trigger_llm_escalation(self):
        result = classify_escalation({
            "patch_proposals": 0,
            "semantic_escalations": 0,
            "safety_blockers": 0,
            "architecture_slices": 40,
            "compatibility_slices": 0,
            "workload_band": "large",
        })
        self.assertEqual(result["tier"], "ARCHITECTURE_REVIEW")
        self.assertEqual(result["b300_gate"], "NOT_APPLICABLE")
        self.assertFalse(result["b300_rental_recommended"])

    def test_large_semantic_pressure_only_marks_long_context_evaluation_candidate(self):
        result = classify_escalation({
            "patch_proposals": 0,
            "semantic_escalations": 3,
            "safety_blockers": 0,
            "architecture_slices": 4,
            "compatibility_slices": 3,
            "workload_band": "large",
        })
        self.assertEqual(result["tier"], "LONG_CONTEXT_EVALUATION_CANDIDATE")
        self.assertEqual(result["b300_gate"], "MEASURE_MODEL_THROUGHPUT_COST_FIRST")
        self.assertFalse(result["b300_rental_recommended"])

    def test_corpus_report_aggregates_and_writes_artifacts(self):
        with TemporaryDirectory() as td, TemporaryDirectory() as out:
            corpus = Path(td)
            repo = corpus / "one"
            repo.mkdir()
            (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            (repo / "requirements.txt").write_text("", encoding="utf-8")
            _baseline(repo)

            manifest = corpus / "manifest.json"
            manifest.write_text(
                json.dumps({
                    "repositories": [
                        {
                            "name": "one",
                            "path": "one",
                            "repo": "example/one",
                            "commit": "abc123",
                        }
                    ]
                }),
                encoding="utf-8",
            )

            result = benchmark_corpus(corpus, manifest_path=manifest)
            self.assertEqual(result["repositories_analyzed"], 1)
            self.assertFalse(result["aggregate"]["b300_rental_recommended"])

            json_path, md_path = write_benchmark(result, out)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertIn("NOT_JUSTIFIED_BY_CURRENT_EVIDENCE", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
