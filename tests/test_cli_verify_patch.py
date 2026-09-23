from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from modfactory.cli import build_parser, main


class VerifyPatchCliTests(unittest.TestCase):
    def test_parser_accepts_behavior_contract(self):
        args = build_parser().parse_args([
            "verify-patch",
            "repo",
            "--patch",
            "candidate.diff",
            "--behavior-contract",
            "behavior.json",
            "--allow-project-code",
        ])
        self.assertEqual(args.command, "verify-patch")
        self.assertEqual(args.behavior_contract, "behavior.json")
        self.assertTrue(args.allow_project_code)

    def test_behavior_contract_requires_project_code_opt_in(self):
        code = main([
            "verify-patch",
            "repo",
            "--patch",
            "candidate.diff",
            "--behavior-contract",
            "behavior.json",
        ])
        self.assertEqual(code, 2)

    def test_behavior_contract_is_forwarded_to_external_verifier(self):
        with TemporaryDirectory() as td:
            out = Path(td) / "out"
            fake_result = {
                "status": "FAIL",
                "reason": "behavior-contract-regression",
                "verification_level": "behavior-contract",
                "patch_artifact": {"sha256": "a" * 64},
            }
            with (
                patch("modfactory.cli.verify_external_patch", return_value=fake_result) as verify,
                patch(
                    "modfactory.cli.write_external_patch_verification",
                    return_value=(out / "verification.json", out / "verification.md"),
                ),
            ):
                code = main([
                    "verify-patch",
                    "repo",
                    "--patch",
                    "candidate.diff",
                    "--behavior-contract",
                    "behavior.json",
                    "--allow-project-code",
                ])

            self.assertEqual(code, 7)
            self.assertEqual(
                verify.call_args.kwargs["behavior_contract"],
                "behavior.json",
            )
            self.assertTrue(verify.call_args.kwargs["allow_project_code"])


if __name__ == "__main__":
    unittest.main()
