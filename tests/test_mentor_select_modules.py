"""Tests of mentor/select_modules.py: a manifest changed only in `version` (the bump every
module change needs, e.g. a new icon) does not call for a consultant sheet.

Run from the repository root: python3 -m unittest discover -s tests
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "mentor" / "select_modules.py"
MODULE = "deltatech_product_icon"
MANIFEST = """# Copyright 2026 Terrabit
{{
    "name": "Product Icon",
    "version": "{version}",
    "depends": [{depends}],
    "license": "LGPL-3",
}}
"""


class TestManifestVersionOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "dev@example.com")
        self.git("config", "user.name", "dev")
        self.write("README.md", "suite\n")
        self.base = self.commit("base")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True,
                              check=True).stdout.strip()

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def manifest(self, version: str, depends: str = '"base"') -> None:
        self.write(f"{MODULE}/__manifest__.py", MANIFEST.format(version=version, depends=depends))

    def selected(self, base: str, head: str) -> list[str]:
        out = subprocess.run([sys.executable, "-I", str(SCRIPT), base, head, "mentor-terrabit"],
                             cwd=self.repo, capture_output=True, text=True, check=True).stdout
        return [m["module"] for m in json.loads(out)["selected"]]

    def test_version_bump_with_icon_is_not_functional(self):
        self.manifest("18.0.1.0.0")
        base = self.commit("module")
        self.manifest("18.0.1.0.1")
        self.write(f"{MODULE}/static/description/icon.png", "png")
        self.write(f"{MODULE}/readme/HISTORY.md", "18.0.1.0.1: icon\n")
        head = self.commit("icon")
        self.assertEqual(self.selected(base, head), [])

    def test_manifest_change_beyond_version_counts(self):
        self.manifest("18.0.1.0.0")
        base = self.commit("module")
        self.manifest("18.0.1.0.1", depends='"base", "stock"')
        head = self.commit("depends")
        self.assertEqual(self.selected(base, head), [MODULE])

    def test_new_module_counts(self):
        self.manifest("18.0.1.0.0")
        head = self.commit("module")
        self.assertEqual(self.selected(self.base, head), [MODULE])

    def test_version_bump_with_model_change_counts(self):
        self.manifest("18.0.1.0.0")
        base = self.commit("module")
        self.manifest("18.0.1.0.1")
        self.write(f"{MODULE}/models/product.py", "# field\n")
        head = self.commit("model")
        self.assertEqual(self.selected(base, head), [MODULE])


if __name__ == "__main__":
    unittest.main()
