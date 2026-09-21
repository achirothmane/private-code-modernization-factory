from __future__ import annotations

import difflib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modfactory.decomposition import (
    aggregate_usage_site_responses,
    build_usage_site_decomposition,
    score_usage_site_response,
)
from modfactory.model_bench import build_model_request, run_model_request
from modfactory.model_eval import build_model_evaluation_plan
from modfactory.scanner import scan_repository


class UsageSiteDecompositionTests(unittest.TestCase):
    def _repo(self, root: Path) -> dict[str, object]:
        (root / "test").mkdir()
        (root / "test" / "a.test.js").write_text(
            "var request = require('request');\n"
            "request.get('http://example.test/a', function () {});\n",
            encoding="utf-8",
        )
        (root / "test" / "b.test.js").write_text(
            "const request = require('request');\n"
            "request.post({ uri: 'http://example.test/b' }, function () {});\n",
            encoding="utf-8",
        )
        (root / "package.json").write_text(
            json.dumps({
                "scripts": {"test": "node test/a.test.js"},
                "devDependencies": {"request": "~2.88.2"},
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "workflows" / "ci.yml").write_text(
            "name: ci\njobs:\n  test:\n    steps:\n      - run: npm test\n",
            encoding="utf-8",
        )
        snapshot = scan_repository(root)
        parent = build_model_evaluation_plan(root, snapshot)
        self.assertEqual(parent["eligible_tasks"], 1, parent)
        parent_task_id = str(parent["tasks"][0]["task_id"])
        return build_usage_site_decomposition(parent, parent_task_id)

    def _diff_for(self, root: Path, target: str) -> str:
        before = (root / target).read_text(encoding="utf-8")
        if target.endswith("a.test.js"):
            after = (
                "var fetch = require('node-fetch');\n"
                "fetch('http://example.test/a').then(function () {});\n"
            )
        else:
            after = (
                "const fetch = require('node-fetch');\n"
                "fetch('http://example.test/b', { method: 'POST' }).then(function () {});\n"
            )
        return "".join(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{target}",
            tofile=f"b/{target}",
        ))

    def _response(self, request: dict[str, object], diff: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "benchmark_id": request["benchmark_id"],
            "task_id": request["task_id"],
            "provider": request["provider"],
            "model": request["model"],
            "unified_diff": diff,
            "rationale": "Migrate one file only.",
            "metrics": {
                "latency_ms": 100.0,
                "input_tokens": 500,
                "output_tokens": 100,
                "cost_usd": None,
            },
        }

    def test_decomposition_creates_one_exact_scope_task_per_usage_site(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            plan = self._repo(root)

            self.assertEqual(plan["eligible_tasks"], 2)
            self.assertEqual(
                plan["usage_sites"],
                ["test/a.test.js", "test/b.test.js"],
            )
            for task in plan["tasks"]:
                self.assertEqual(task["task_kind"], "usage-site")
                self.assertEqual(task["allowed_changes"], [task["target"]])
                self.assertEqual(
                    [item["role"] for item in task["context_files"]],
                    ["manifest-readonly", "usage-site"],
                )
                self.assertNotIn("package.json", task["allowed_changes"])
                self.assertFalse(task["requires_full_repository_context"])
                self.assertEqual(task["response_mode"], "replacement-content")

    def test_replacement_content_is_converted_to_deterministic_unified_diff(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            plan = self._repo(root)
            task = plan["tasks"][0]
            request = build_model_request(
                plan,
                str(task["task_id"]),
                provider="fixture",
                model="fixture-model",
            )
            target = str(task["target"])
            replacement = (
                "var fetch = require('node-fetch');\n"
                "fetch('http://example.test/a').then(function () {});\n"
            )

            class FakeAdapter:
                provider = "fixture"
                model = "fixture-model"

                def invoke(self, _request):
                    return {
                        "replacement_content": replacement,
                        "rationale": "Migrate one usage-site.",
                        "usage": {"input_tokens": 300, "output_tokens": 80},
                        "cost_usd": None,
                    }

            response = run_model_request(request, FakeAdapter())
            self.assertEqual(response["provider_response_mode"], "replacement-content")
            self.assertEqual(len(response["replacement_sha256"]), 64)
            self.assertIn(f"--- a/{target}", response["unified_diff"])
            self.assertIn(f"+++ b/{target}", response["unified_diff"])
            self.assertIn("+var fetch = require('node-fetch');", response["unified_diff"])

            score = score_usage_site_response(root, request, response)
            self.assertEqual(score["status"], "REVIEW", score)
            self.assertEqual(score["dependency_requirements"], ["node-fetch"])

    def test_partial_score_accepts_one_file_and_reports_new_dependency(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            plan = self._repo(root)
            task = plan["tasks"][0]
            request = build_model_request(
                plan,
                str(task["task_id"]),
                provider="fixture",
                model="fixture-model",
            )
            response = self._response(
                request,
                self._diff_for(root, str(task["target"])),
            )

            score = score_usage_site_response(root, request, response)

            self.assertEqual(score["status"], "REVIEW", score)
            self.assertEqual(score["reason"], "partial-static-pass-manifest-not-finalized")
            self.assertTrue(score["gates"]["exact_single_file_scope"])
            self.assertTrue(score["gates"]["local_legacy_usage_removed"])
            self.assertEqual(score["dependency_requirements"], ["node-fetch"])
            self.assertEqual(score["static_quality"]["ratio"], 1.0)

    def test_partial_score_rejects_package_json_change(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            plan = self._repo(root)
            task = plan["tasks"][0]
            request = build_model_request(
                plan,
                str(task["task_id"]),
                provider="fixture",
                model="fixture-model",
            )
            target_diff = self._diff_for(root, str(task["target"]))
            before = (root / "package.json").read_text(encoding="utf-8")
            after = before.replace('"request": "~2.88.2"', '"node-fetch": "2.7.0"')
            manifest_diff = "".join(difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile="a/package.json",
                tofile="b/package.json",
            ))
            response = self._response(request, target_diff + manifest_diff)

            score = score_usage_site_response(root, request, response)

            self.assertEqual(score["status"], "FAIL")
            self.assertEqual(score["reason"], "single-file-scope-violation")

    def test_aggregate_requires_every_usage_site_then_becomes_manifest_ready(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            plan = self._repo(root)
            requests = []
            responses = []
            for task in plan["tasks"]:
                request = build_model_request(
                    plan,
                    str(task["task_id"]),
                    provider="fixture",
                    model="fixture-model",
                )
                requests.append(request)
                responses.append(self._response(
                    request,
                    self._diff_for(root, str(task["target"])),
                ))

            partial = aggregate_usage_site_responses(
                root,
                plan,
                requests[:1],
                responses[:1],
            )
            self.assertEqual(partial["status"], "PARTIAL")
            self.assertEqual(partial["accepted_usage_sites"], 1)
            self.assertEqual(len(partial["missing_targets"]), 1)

            aggregate = aggregate_usage_site_responses(
                root,
                plan,
                requests,
                responses,
            )
            self.assertEqual(aggregate["status"], "READY_FOR_MANIFEST_FINALIZATION", aggregate)
            self.assertEqual(aggregate["accepted_usage_sites"], 2)
            self.assertEqual(aggregate["remaining_legacy_usage"], [])
            self.assertEqual(aggregate["dependency_requirements"], ["node-fetch"])
            self.assertFalse(aggregate["manifest_finalized"])
            self.assertIn("test/a.test.js", aggregate["aggregate_diff"])
            self.assertIn("test/b.test.js", aggregate["aggregate_diff"])


if __name__ == "__main__":
    unittest.main()
