from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modfactory.recipes import build_recipe_instances, recipe_for_finding
from modfactory.scanner import scan_repository
from modfactory.slices import build_migration_slices


class RecipeTests(unittest.TestCase):
    def test_imp_and_distutils_findings_receive_deterministic_recipes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "setup.py").write_text(
                "from distutils.core import setup\n",
                encoding="utf-8",
            )
            (root / "app.py").write_text(
                "import imp\nplugin = imp.find_module('x')\n",
                encoding="utf-8",
            )
            (root / "tests").mkdir()
            (root / "tests" / "test_app.py").write_text("def test_x(): assert True\n", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
            snap = scan_repository(root)

            recipe_ids = {r["id"] for r in build_recipe_instances(snap.findings)}
            self.assertIn("python-imp-to-importlib", recipe_ids)
            self.assertIn("python-distutils-to-setuptools", recipe_ids)

            slices = [s for s in build_migration_slices(snap) if s["kind"] == "compatibility"]
            self.assertEqual(len(slices), 2)
            self.assertTrue(all(s["recipe"] is not None for s in slices))
            imp_slice = next(s for s in slices if "imp module" in s["title"])
            self.assertTrue(any("module-loading" in p for p in imp_slice["preconditions"]))
            self.assertTrue(any("baseline test" in r.lower() for r in imp_slice["rollback_triggers"]))

    def test_advisory_recipe_does_not_claim_mechanical_replacement(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "App.java").write_text("import javax.servlet.Filter;\n", encoding="utf-8")
            (root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "Test.java").write_text("class Test {}\n", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
            snap = scan_repository(root)
            finding = next(f for f in snap.findings if f.message == "Javax namespace detected")
            recipe = recipe_for_finding(finding)
            self.assertIsNotNone(recipe)
            self.assertEqual(recipe.confidence, "advisory")
            self.assertIn("Do not apply global text replacement.", recipe.transforms)


if __name__ == "__main__":
    unittest.main()
