from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modfactory.cli import main


ROOT = Path(__file__).resolve().parents[1]


class QuickstartExamplesTests(unittest.TestCase):
    def test_snapshot_oracle_quickstart_is_blocked(self):
        with TemporaryDirectory() as td:
            code = main([
                "verify-patch",
                str(ROOT / "examples" / "quickstart" / "repo"),
                "--patch",
                str(ROOT / "examples" / "quickstart" / "candidate.diff"),
                "--producer",
                "demo",
                "--output",
                td,
            ])
        self.assertEqual(code, 5)

    def test_behavior_contract_quickstart_fails_on_candidate(self):
        with TemporaryDirectory() as td:
            code = main([
                "verify-patch",
                str(ROOT / "examples" / "behavior-contract" / "repo"),
                "--patch",
                str(ROOT / "examples" / "behavior-contract" / "candidate.diff"),
                "--behavior-contract",
                str(ROOT / "examples" / "behavior-contract" / "behavior.json"),
                "--allow-project-code",
                "--producer",
                "demo",
                "--output",
                td,
            ])
        self.assertEqual(code, 7)


if __name__ == "__main__":
    unittest.main()
