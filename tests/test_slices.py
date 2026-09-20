from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modfactory.scanner import scan_repository
from modfactory.slices import build_migration_slices


class MigrationSliceTests(unittest.TestCase):
    def test_safety_slices_precede_code_changes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.py").write_text("import imp\n", encoding="utf-8")
            (root / "requirements.txt").write_text("x==1\n", encoding="utf-8")
            slices = build_migration_slices(scan_repository(root))
            kinds = [s["kind"] for s in slices]
            self.assertEqual(kinds[:2], ["safety", "safety"])
            compatibility = next(s for s in slices if s["kind"] == "compatibility")
            self.assertEqual(compatibility["target"], "app.py")
            self.assertIn("CI baseline is green", compatibility["preconditions"])


if __name__ == "__main__":
    unittest.main()
