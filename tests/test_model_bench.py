from __future__ import annotations

import difflib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modfactory.model_bench import (
    build_model_request,
    inspect_unified_diff,
    score_model_response,
    validate_response_envelope,
    write_model_request,
    write_model_score,
)
from modfactory.model_eval import build_model_evaluation_plan
from modfactory.scanner import scan_repository


class ModelBenchmarkTests(unittest.TestCase):
    def _request_repo(self, root: Path) -> tuple[dict[str, object], dict[str, object]]:
        (root / "test").mkdir()
        (root / "test" / "a.test.js").write_text(
            "var request = require('request');\n"
            "request.get('http://example.test', function () {});\n",
            encoding="utf-8",
        )
        (root / "test" / "b.test.js").write_text(
            "const request = require('request');\n"
            "request.post({ uri: 'http://example.test' }, function () {});\n",
            encoding="utf-8",
        )
        package = {
            "scripts": {"test": "node test/a.test.js"},
            "devDependencies": {"request": "~2.88.2"},
        }
        (root / "package.json").write_text(
            json.dumps(package, indent=2) + "\n",
            encoding="utf-8",
        )
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "workflows" / "ci.yml").write_text(
            "name: ci\njobs:\n  test:\n    steps:\n      - run: npm test\n",
            encoding="utf-8",
        )

        snapshot = scan_repository(root)
        plan = build_model_evaluation_plan(root, snapshot)
        self.assertEqual(plan["eligible_tasks"], 1, plan)
        task_id = str(plan["tasks"][0]["task_id"])
        request = build_model_request(
            plan,
            task_id,
            provider="example-provider",
            model="ordinary-model",
        )
        return plan, request

    def _valid_diff(self, root: Path) -> str:
        changes = {
            "package.json": (
                json.dumps({
                    "scripts": {"test": "node test/a.test.js"},
                    "devDependencies": {"node-fetch": "2.7.0"},
                }, indent=2) + "\n"
            ),
            "test/a.test.js": (
                "var fetch = require('node-fetch');\n"
                "fetch('http://example.test').then(function () {});\n"
            ),
            "test/b.test.js": (
                "const fetch = require('node-fetch');\n"
                "fetch('http://example.test', { method: 'POST' }).then(function () {});\n"
            ),
        }
        chunks = []
        for rel, after in changes.items():
            before = (root / rel).read_text(encoding="utf-8")
            chunks.extend(difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            ))
        return "".join(chunks)

    def _response(self, request: dict[str, object], diff: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "benchmark_id": request["benchmark_id"],
            "task_id": request["task_id"],
            "provider": request["provider"],
            "model": request["model"],
            "unified_diff": diff,
            "rationale": "Replace deprecated request usage with a maintained HTTP client.",
            "metrics": {
                "latency_ms": 1250.5,
                "input_tokens": 6000,
                "output_tokens": 900,
                "cost_usd": 0.0123,
            },
        }

    def test_valid_provider_response_scores_static_review_without_touching_original(self):
        with TemporaryDirectory() as td, TemporaryDirectory() as out:
            root = Path(td)
            _, request = self._request_repo(root)
            diff = self._valid_diff(root)
            response = self._response(request, diff)
            original = (root / "package.json").read_text(encoding="utf-8")

            score = score_model_response(root, request, response)

            self.assertEqual(score["status"], "REVIEW", score)
            self.assertEqual(score["reason"], "static-pass-project-tests-not-executed")
            self.assertTrue(score["gates"]["scope_compliant"])
            self.assertTrue(score["gates"]["patch_applies_cleanly"])
            self.assertTrue(score["gates"]["target_finding_removed"])
            self.assertTrue(score["gates"]["legacy_usage_removed"])
            self.assertTrue(score["gates"]["no_new_findings"])
            self.assertEqual(score["static_quality"]["ratio"], 1.0)
            self.assertEqual(score["metrics"]["input_tokens"], 6000)
            self.assertEqual((root / "package.json").read_text(encoding="utf-8"), original)

            request_path = write_model_request(request, out)
            json_path, md_path = write_model_score(score, out)
            self.assertTrue(request_path.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

    def test_out_of_scope_file_is_rejected_before_patch_application(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _, request = self._request_repo(root)
            (root / "README.md").write_text("old\n", encoding="utf-8")
            diff = "".join(difflib.unified_diff(
                ["old\n"],
                ["new\n"],
                fromfile="a/README.md",
                tofile="b/README.md",
            ))
            response = self._response(request, diff)

            score = score_model_response(root, request, response)

            self.assertEqual(score["status"], "FAIL")
            self.assertEqual(score["reason"], "allowed-scope-violation")
            self.assertEqual(score["gates"]["scope_violations"], ["README.md"])

    def test_repository_change_after_request_creation_blocks_scoring(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _, request = self._request_repo(root)
            response = self._response(request, self._valid_diff(root))
            (root / "test" / "a.test.js").write_text(
                "// changed after benchmark request\n",
                encoding="utf-8",
            )

            score = score_model_response(root, request, response)

            self.assertEqual(score["status"], "FAIL")
            self.assertEqual(score["reason"], "repository-baseline-mismatch")
            self.assertEqual(
                score["baseline_mismatches"][0]["reason"],
                "context-sha256-mismatch",
            )

    def test_task_tampering_after_request_creation_blocks_scoring(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _, request = self._request_repo(root)
            response = self._response(request, self._valid_diff(root))
            request["task"]["objective"] = "tampered objective"

            score = score_model_response(root, request, response)

            self.assertEqual(score["status"], "FAIL")
            self.assertEqual(score["reason"], "request-integrity-invalid")
            self.assertIn("request-task-sha256-mismatch", score["request_errors"])

    def test_response_metrics_must_be_provider_values_or_null(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _, request = self._request_repo(root)
            response = self._response(request, self._valid_diff(root))
            response["metrics"]["latency_ms"] = "about one second"
            response["metrics"]["input_tokens"] = -1

            valid, errors, _ = validate_response_envelope(request, response)

            self.assertFalse(valid)
            self.assertIn("metrics.latency_ms-must-be-a-non-negative-number-or-null", errors)
            self.assertIn("metrics.input_tokens-must-be-a-non-negative-integer-or-null", errors)

    def test_diff_creation_deletion_and_path_traversal_are_blocked(self):
        created = inspect_unified_diff(
            "--- /dev/null\n+++ b/new.js\n@@ -0,0 +1 @@\n+hello\n"
        )
        traversal = inspect_unified_diff(
            "--- a/good.js\n+++ b/../escape.js\n@@ -1 +1 @@\n-old\n+new\n"
        )

        self.assertFalse(created["valid"])
        self.assertFalse(traversal["valid"])


if __name__ == "__main__":
    unittest.main()
