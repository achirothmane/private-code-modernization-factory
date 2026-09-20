from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .patches import DEFAULT_DIFF_BUDGET, build_patch_proposal, write_patch_proposal
from .report import write_report
from .scanner import scan_repository


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "analyze":
        snapshot = scan_repository(args.repository)
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
        snapshot = scan_repository(args.repository)
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

    return 1


if __name__ == "__main__":
    sys.exit(main())
