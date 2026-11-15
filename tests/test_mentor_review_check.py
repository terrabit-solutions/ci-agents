"""Tests of mentor/review_check.py: the `consultant_sheet` manifest key decides what the precheck
asks for. `simple` is a sheet without screenshots, `none` needs no sheet, no key means `full`.

Run from the repository root: python3 -m unittest discover -s tests
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_check", ROOT / "mentor" / "review_check.py")
review_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review_check)

MODULE = "l10n_ro_partner_cnp"
SHEET = """# Fișă Modul: test

## 1. Scop

## 2. Bază legală

## 3. Roluri

## 4. Configurare

## 5. Date

## 6. Flux de utilizare

### Pasul 1 — Completarea CNP-ului

Text fără captură.

### Pasul 2 — Validarea la salvare

Tot fără captură.

## 7. Note contabile

## 8. Rapoarte

## 9. Erori

## 10. Limitări

## 11. Verificări
"""


class TestConsultantSheetMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def make(self, mode=None, sheet=SHEET, shots=()):
        key = f'    "consultant_sheet": "{mode}",\n' if mode else ""
        Path(MODULE, "readme").mkdir(parents=True)
        Path(MODULE, "__manifest__.py").write_text(
            f'# Copyright 2026 Terrabit\n{{\n    "name": "CNP",\n    "version": "19.0.1.0.0",\n{key}}}\n',
            encoding="utf-8",
        )
        if sheet is not None:
            Path(MODULE, review_check.FISA).write_text(sheet, encoding="utf-8")
        for shot in shots:
            Path(MODULE, "static", "description").mkdir(parents=True, exist_ok=True)
            Path(MODULE, "static", "description", shot).write_bytes(b"png")

    def texts(self, result):
        return [f["text"] for f in result["findings"]]

    def test_full_by_default_asks_for_screenshots(self):
        self.make(shots=("01_unused.png",))
        result = review_check.check_module(MODULE, set())
        self.assertEqual(result["consultant_sheet"], "full")
        self.assertTrue(any(t.startswith("Pași fără captură") for t in self.texts(result)))
        self.assertTrue(any(t.startswith("Capturi din modul nefolosite") for t in self.texts(result)))

    def test_simple_needs_no_screenshots(self):
        self.make("simple", shots=("01_unused.png",))
        result = review_check.check_module(MODULE, set())
        self.assertEqual(result["consultant_sheet"], "simple")
        self.assertEqual(result["findings"], [])

    def test_simple_still_needs_the_sheet(self):
        self.make("simple", sheet=None)
        self.assertEqual(review_check.check_module(MODULE, set())["findings"][0]["severity"], "critic")

    def test_simple_still_checks_structure_and_placeholders(self):
        self.make("simple", sheet=SHEET.replace("## 9. Erori\n", "") + "\n[SCREENSHOT: x]\n")
        texts = self.texts(review_check.check_module(MODULE, set()))
        self.assertTrue(any("secțiunile 9" in t for t in texts))
        self.assertTrue(any("[SCREENSHOT:" in t for t in texts))

    def test_none_needs_no_sheet(self):
        self.make("none", sheet=None)
        result = review_check.check_module(MODULE, set())
        self.assertEqual(result["findings"], [])
        Path("pre.json").write_text(json.dumps([result]), encoding="utf-8")
        merged = review_check.merge("pre.json", "missing.json")
        self.assertEqual(merged[0]["verdict"], "fără fișă (consultant_sheet: none)")
        self.assertEqual(merged[0]["findings"], [])

    def test_unknown_value_or_bad_manifest_is_full(self):
        self.make("maybe")
        self.assertEqual(review_check.sheet_mode(MODULE), "full")
        Path(MODULE, "__manifest__.py").write_text("{not python", encoding="utf-8")
        self.assertEqual(review_check.sheet_mode(MODULE), "full")


if __name__ == "__main__":
    unittest.main()
