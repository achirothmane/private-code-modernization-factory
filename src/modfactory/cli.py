from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    return 1


if __name__ == "__main__":
    sys.exit(main())
