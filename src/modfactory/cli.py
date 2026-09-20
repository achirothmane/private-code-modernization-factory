from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .benchmark import benchmark_corpus, write_benchmark
from .patches import DEFAULT_DIFF_BUDGET, build_patch_proposal, write_patch_proposal
from .model_eval import build_model_evaluation_plan, write_model_evaluation_plan
from .model_bench import (
    GitHubModelsAdapter,
    build_model_request,
    load_request,
    load_response,
    run_model_request,
    score_model_response,
    write_model_request,
    write_model_response,
    write_model_score,
)
from .report import write_report
from .scanner import scan_repository
from .verification import build_differential_verification, write_verification
from .targets import parse_target_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modfactory",
        description="Evidence-first repository modernization analyzer",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Analyze a repository and produce modernization evidence")
    analyze.add_argument("repository", help="Path to repository")
    analyze.add_argument("--output", default=".modfactory", help="Output directory")
    analyze.add_argument("--fail-on", choices=["none", "high", "critical"], default="none",
                         help="Exit non-zero at/above a risk band")

    propose = sub.add_parser("propose", help="Generate a review-only patch proposal for one migration slice")
    propose.add_argument("repository", help="Path to repository")
    propose.add_argument("--slice-id", required=True, help="Migration slice ID from the analysis report")
    propose.add_argument("--output", default=".modfactory", help="Output directory")
    propose.add_argument("--diff-budget", type=int, default=DEFAULT_DIFF_BUDGET,
                         help="Maximum added+removed lines allowed in a proposal")

    verify = sub.add_parser("verify", help="Verify one proposed migration slice in temporary before/after copies")
    verify.add_argument("repository", help="Path to repository")
    verify.add_argument("--slice-id", required=True, help="Migration slice ID from the analysis report")
    verify.add_argument("--output", default=".modfactory", help="Output directory")
    verify.add_argument("--diff-budget", type=int, default=DEFAULT_DIFF_BUDGET,
                        help="Maximum added+removed lines allowed in the underlying proposal")
    verify.add_argument("--allow-project-code", action="store_true",
                        help="Explicitly allow discovered test commands to run in temporary copies")
    verify.add_argument("--timeout", type=int, default=120,
                        help="Per-command timeout in seconds when project-code execution is enabled")

    bench = sub.add_parser("benchmark", help="Measure deterministic coverage and escalation pressure across a local corpus")
    bench.add_argument("corpus", help="Directory containing repository subdirectories")
    bench.add_argument("--manifest", help="Optional JSON manifest with repository metadata and relative paths")
    bench.add_argument("--output", default=".modfactory", help="Output directory")
    bench.add_argument("--diff-budget", type=int, default=DEFAULT_DIFF_BUDGET,
                       help="Maximum added+removed lines allowed when probing deterministic proposals")

    eval_plan = sub.add_parser(
        "eval-plan",
        help="Build a context-minimized, non-executing model evaluation plan for semantic migration tasks",
    )
    eval_plan.add_argument("repository", help="Path to repository")
    eval_plan.add_argument("--output", default=".modfactory", help="Output directory")
    eval_plan.add_argument("--diff-budget", type=int, default=DEFAULT_DIFF_BUDGET,
                           help="Maximum added+removed lines allowed when probing deterministic proposals")

    model_request = sub.add_parser(
        "model-request",
        help="Build a provider-neutral request artifact for one eligible model-evaluation task",
    )
    model_request.add_argument("plan", help="Path to model-eval plan.json")
    model_request.add_argument("--task-id", required=True, help="Task ID from the model-evaluation plan")
    model_request.add_argument("--provider", required=True, help="Provider identifier to record in the benchmark contract")
    model_request.add_argument("--model", required=True, help="Model identifier to record in the benchmark contract")
    model_request.add_argument("--output", default=".modfactory", help="Output directory")

    model_score = sub.add_parser(
        "model-score",
        help="Score one provider response against scope, static evidence, and optional project tests",
    )
    model_score.add_argument("repository", help="Path to repository")
    model_score.add_argument("--request", required=True, help="Path to model-bench request.json")
    model_score.add_argument("--response", required=True, help="Path to provider response JSON")
    model_score.add_argument("--output", default=".modfactory", help="Output directory")
    model_score.add_argument("--allow-project-code", action="store_true",
                             help="Explicitly allow discovered project test commands in temporary copies")
    model_score.add_argument("--timeout", type=int, default=120,
                             help="Per-command timeout in seconds when project-code execution is enabled")

    github_run = sub.add_parser(
        "model-run-github",
        help="Run one provider-neutral benchmark request through GitHub Models using GITHUB_TOKEN",
    )
    github_run.add_argument("--request", required=True, help="Path to model-bench request.json")
    github_run.add_argument("--output", default=".modfactory", help="Output directory")
    github_run.add_argument("--timeout", type=int, default=120, help="Inference timeout in seconds")
    github_run.add_argument("--max-tokens", type=int, default=8192, help="Maximum completion tokens")
    for command_parser in (analyze, propose, verify, bench, eval_plan):
        command_parser.add_argument(
            "--target",
            action="append",
            default=[],
            metavar="KEY=VERSION",
            help=(
                "Explicit modernization target; repeatable. "
                "Supported keys: react-dom, spring-boot, python."
            ),
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        target_profile = parse_target_args(getattr(args, "target", []))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.command == "analyze":
        snapshot = scan_repository(args.repository, targets=target_profile)
        json_path, md_path = write_report(snapshot, args.output)
        harness_dir = Path(args.output) / "harness"
        print(f"Risk: {snapshot.risk_score}/100 ({snapshot.risk_band})")
        print(f"JSON: {json_path}")
        print(f"Markdown: {md_path}")
        print(f"Harness: {harness_dir / 'harness.json'}")
        print(f"Baseline script: {harness_dir / 'baseline.sh'}")
        thresholds = {"high": 45, "critical": 70}
        if args.fail_on != "none" and snapshot.risk_score >= thresholds[args.fail_on]:
            return 2
        return 0

    if args.command == "propose":
        if args.diff_budget < 1:
            print("--diff-budget must be >= 1", file=sys.stderr)
            return 2
        snapshot = scan_repository(args.repository, targets=target_profile)
        proposal = build_patch_proposal(
            args.repository,
            snapshot,
            args.slice_id,
            diff_budget=args.diff_budget,
        )
        json_path, diff_path = write_patch_proposal(proposal, args.output)
        print(f"Patch proposal: {proposal['status']}")
        print(f"Reason: {proposal['reason']}")
        print(f"JSON: {json_path}")
        print(f"Diff: {diff_path}")
        return 0 if proposal["status"] == "PROPOSED" else 3

    if args.command == "verify":
        if args.diff_budget < 1:
            print("--diff-budget must be >= 1", file=sys.stderr)
            return 2
        if args.timeout < 1:
            print("--timeout must be >= 1", file=sys.stderr)
            return 2
        snapshot = scan_repository(args.repository, targets=target_profile)
        result = build_differential_verification(
            args.repository,
            snapshot,
            args.slice_id,
            diff_budget=args.diff_budget,
            allow_project_code=args.allow_project_code,
            timeout_seconds=args.timeout,
        )
        json_path, md_path = write_verification(result, args.output)
        print(f"Verification: {result['status']}")
        print(f"Reason: {result['reason']}")
        print(f"Level: {result['verification_level']}")
        print(f"JSON: {json_path}")
        print(f"Markdown: {md_path}")
        if result["status"] == "PASS":
            return 0
        if result["status"] == "REVIEW":
            return 4
        return 5

    if args.command == "eval-plan":
        if args.diff_budget < 1:
            print("--diff-budget must be >= 1", file=sys.stderr)
            return 2
        snapshot = scan_repository(args.repository, targets=target_profile)
        plan = build_model_evaluation_plan(
            args.repository,
            snapshot,
            diff_budget=args.diff_budget,
        )
        json_path, jsonl_path, md_path = write_model_evaluation_plan(plan, args.output)
        print(f"Eligible model tasks: {plan['eligible_tasks']}")
        print(f"Blocked model tasks: {plan['blocked_tasks']}")
        print(f"Next compute gate: {plan['compute_policy']['next_gate']}")
        print(f"JSON: {json_path}")
        print(f"JSONL: {jsonl_path}")
        print(f"Markdown: {md_path}")
        return 0

    if args.command == "model-request":
        try:
            plan = load_request(args.plan)
            request = build_model_request(
                plan,
                args.task_id,
                provider=args.provider,
                model=args.model,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        path = write_model_request(request, args.output)
        print(f"Benchmark ID: {request['benchmark_id']}")
        print(f"Task: {request['task_id']}")
        print(f"Provider: {request['provider']}")
        print(f"Model: {request['model']}")
        print("Provider invoked: false")
        print(f"Request: {path}")
        return 0

    if args.command == "model-run-github":
        if args.timeout < 1 or args.max_tokens < 1:
            print("--timeout and --max-tokens must be >= 1", file=sys.stderr)
            return 2
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            print("GITHUB_TOKEN is required for GitHub Models inference", file=sys.stderr)
            return 8
        try:
            request = load_request(args.request)
            if request.get("provider") != "github-models":
                print("Request provider must be 'github-models'", file=sys.stderr)
                return 2
            model = str(request.get("model", ""))
            adapter = GitHubModelsAdapter(
                token=token,
                model=model,
                timeout_seconds=args.timeout,
                max_tokens=args.max_tokens,
            )
            response = run_model_request(request, adapter)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(str(exc), file=sys.stderr)
            return 9
        path = write_model_response(response, args.output)
        metrics = response.get("metrics", {})
        print(f"Provider: {response['provider']}")
        print(f"Model requested: {response['model']}")
        print(f"Model returned: {response.get('provider_model_returned')}")
        print(f"Latency ms: {metrics.get('latency_ms') if isinstance(metrics, dict) else None}")
        print(f"Input tokens: {metrics.get('input_tokens') if isinstance(metrics, dict) else None}")
        print(f"Output tokens: {metrics.get('output_tokens') if isinstance(metrics, dict) else None}")
        print(f"Cost USD: {metrics.get('cost_usd') if isinstance(metrics, dict) else None}")
        print(f"Response: {path}")
        return 0

    if args.command == "model-score":
        if args.timeout < 1:
            print("--timeout must be >= 1", file=sys.stderr)
            return 2
        try:
            request = load_request(args.request)
            response = load_response(args.response)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        score = score_model_response(
            args.repository,
            request,
            response,
            allow_project_code=args.allow_project_code,
            timeout_seconds=args.timeout,
        )
        json_path, md_path = write_model_score(score, args.output)
        print(f"Score status: {score['status']}")
        print(f"Reason: {score['reason']}")
        print(f"JSON: {json_path}")
        print(f"Markdown: {md_path}")
        if score["status"] == "PASS":
            return 0
        if score["status"] == "REVIEW":
            return 4
        if score["status"] == "BLOCKED":
            return 5
        return 7

    if args.command == "benchmark":
        if args.diff_budget < 1:
            print("--diff-budget must be >= 1", file=sys.stderr)
            return 2
        result = benchmark_corpus(
            args.corpus,
            manifest_path=args.manifest,
            diff_budget=args.diff_budget,
            targets=target_profile,
        )
        json_path, md_path = write_benchmark(result, args.output)
        print(f"Repositories: {result['repositories_analyzed']}/{result['repositories_requested']}")
        print(f"Elapsed: {result['elapsed_seconds']}s")
        print(f"JSON: {json_path}")
        print(f"Markdown: {md_path}")
        return 0 if not result["errors"] else 6

    return 1


if __name__ == "__main__":
    sys.exit(main())
