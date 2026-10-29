"""Tests of argus/inline.py: the anchor of an inline comment and the duplicate threads.

Run from the repository root: python3 -m unittest discover -s tests
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "argus"))

import inline  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PATH = "l10n_ro_anaf_d394/tests/test_d394_report.py"
RULE_BODY = ("**[minor]** Pe 20.0 `res.partner.is_company` este calculat și nu se mai scrie, "
             "nici în teste. Scoate cheia din `create`.")

# The PR only drops "is_company" from a partner created in a test.
REMOVES = """\
@@ -10,7 +10,6 @@ class TestD394(TestCommon):
     def test_partner(self):
         \"\"\"Partenerul DE al testului TC-19b.\"\"\"
         partner = self.env["res.partner"].create({
             "name": "DE GmbH",
-            "is_company": True,
             "vat": "DE123456789",
         })
         self.assertTrue(partner)"""

# The PR writes it.
ADDS = """\
@@ -10,6 +10,7 @@ class TestD394(TestCommon):
     def test_partner(self):
         \"\"\"Partenerul DE al testului TC-19b.\"\"\"
         partner = self.env["res.partner"].create({
             "name": "DE GmbH",
+            "is_company": True,
             "vat": "DE123456789",
         })
         self.assertTrue(partner)"""


def findings(patch: str, fragment: str) -> list[int]:
    return inline.added_matches(inline.parse_patch(patch), fragment)


class TestPatch(unittest.TestCase):
    def test_parse_right_side(self):
        side = inline.parse_patch(ADDS)
        self.assertEqual(side["added"], {14: '            "is_company": True,'})
        self.assertEqual(sorted(side["context"]), [10, 11, 12, 13, 15, 16, 17])
        side = inline.parse_patch(REMOVES)
        self.assertEqual(side["added"], {})
        self.assertEqual(side["removed"], ['            "is_company": True,'])
        self.assertEqual(sorted(side["context"]), [10, 11, 12, 13, 14, 15, 16])


class TestFindings(unittest.TestCase):
    def test_removed_pattern_is_no_finding(self):
        self.assertEqual(findings(REMOVES, '"is_company"'), [])

    def test_added_pattern_is_one_finding(self):
        self.assertEqual(findings(ADDS, '"is_company"'), [14])

    def test_pr_1005(self):
        """The real diff of l10n_ro_ent#1005: is_company only goes away in the tests."""
        patch = (FIXTURES / "l10n_ro_ent_1005_test_d394_report.patch").read_text(encoding="utf-8")
        side = inline.parse_patch(patch)
        self.assertEqual(inline.added_matches(side, "is_company"), [])
        self.assertTrue(any("is_company" in t for t in side["removed"]))
        # Line 1863, the docstring the comment was posted on more than ten times.
        self.assertIn(1863, side["added"])
        reason = inline.check_anchor(side, 1863, 1863, "is_company")
        self.assertIn("doar îl șterge", reason)
        self.assertIsNotNone(inline.check_anchor(side, 1863, 1863, "is_company", context=True))


class TestAnchor(unittest.TestCase):
    def test_refuses_every_line_when_the_pr_only_removes(self):
        side = inline.parse_patch(REMOVES)
        for n in range(10, 17):
            self.assertIsNotNone(inline.check_anchor(side, n, n, '"is_company"', context=True), n)
        self.assertIn("doar șterge", inline.check_anchor(side, 12, 12, "Partenerul", context=True))

    def test_accepts_the_added_line(self):
        side = inline.parse_patch(ADDS)
        self.assertIsNone(inline.check_anchor(side, 14, 14, '"is_company"'))
        self.assertIsNone(inline.check_anchor(side, 12, 15, '"is_company"'))

    def test_points_to_the_added_line(self):
        side = inline.parse_patch(ADDS)
        reason = inline.check_anchor(side, 11, 11, '"is_company"')
        self.assertIn("Apare pe liniile adăugate 14", reason)

    def test_line_outside_the_right_side(self):
        side = inline.parse_patch(ADDS)
        self.assertIn("nu sunt în partea dreaptă", inline.check_anchor(side, 40, 40, "x"))
        self.assertIn("nu e în diff", inline.check_anchor(None, 14, 14, "x"))

    def test_context_only_when_asked_and_next_to_an_added_line(self):
        side = inline.parse_patch(ADDS)
        self.assertIsNotNone(inline.check_anchor(side, 15, 15, '"vat"'))
        self.assertIsNone(inline.check_anchor(side, 15, 15, '"vat"', context=True))

    def test_empty_match(self):
        side = inline.parse_patch(ADDS)
        self.assertIn("--match e gol", inline.check_anchor(side, 14, 14, " "))


def comment(cid, body, path=PATH, login="argus-terrabit[bot]", reply_to=None):
    return {"id": cid, "path": path, "body": body, "in_reply_to_id": reply_to,
            "html_url": f"https://github.com/x/y/pull/1#discussion_r{cid}", "user": {"login": login}}


class TestDuplicates(unittest.TestCase):
    def setUp(self):
        self.side = inline.parse_patch(ADDS)
        self.digest = inline.line_hash(self.side, 14, 14)
        self.body = f"{RULE_BODY}\n\n{inline.marker('o20-is-company', self.digest)}"

    def test_same_rule_same_line_is_a_duplicate(self):
        found = inline.find_duplicate([comment(1, self.body)], PATH, "o20-is-company", self.digest, RULE_BODY)
        self.assertEqual(found["id"], 1)

    def test_mentor_thread_counts_too(self):
        found = inline.find_duplicate([comment(2, self.body, login="mentor-terrabit[bot]")],
                                      PATH, "o20-is-company", self.digest, RULE_BODY)
        self.assertEqual(found["id"], 2)

    def test_changed_line_is_posted_again(self):
        changed = inline.line_hash(inline.parse_patch(ADDS.replace("True", "False")), 14, 14)
        self.assertNotEqual(changed, self.digest)
        self.assertIsNone(inline.find_duplicate([comment(1, self.body)], PATH, "o20-is-company", changed, RULE_BODY))

    def test_other_rule_file_author_or_reply_is_not_a_duplicate(self):
        others = [
            comment(1, self.body, path="other.py"),
            comment(2, self.body, login="dhongu"),
            comment(3, self.body, reply_to=99),
            comment(4, f"{RULE_BODY}\n\n{inline.marker('o20-get-param', self.digest)}"),
        ]
        self.assertIsNone(inline.find_duplicate(others, PATH, "o20-is-company", self.digest, RULE_BODY))

    def test_thread_from_before_the_marker(self):
        """The comments already on l10n_ro_ent#1005 have no marker: matched on their first line."""
        found = inline.find_duplicate([comment(5, RULE_BODY)], PATH, "o20-is-company", self.digest, RULE_BODY)
        self.assertEqual(found["id"], 5)


class FakeGh:
    """Stands in for `gh api`: the PR's files and comments, and the POSTs made."""

    def __init__(self, patch, comments):
        self.patch, self.comments, self.posted = patch, comments, []

    def __call__(self, cmd, **kwargs):
        args = cmd[2:]
        if "-X" in args:
            self.posted.append(args)
            return mock.Mock(stdout="")
        if args[1].endswith("/files"):
            rows = [{"filename": PATH, "patch": self.patch}]
        else:
            rows = self.comments
        return mock.Mock(stdout="\n".join(json.dumps(r) for r in rows))


class TestMain(unittest.TestCase):
    ENV = {"REPO": "terrabit-solutions/l10n_ro_ent", "PR_NUMBER": "1005", "HEAD_SHA": "abc123"}

    def run_main(self, gh, line=14):
        argv = ["inline.py", "--path", PATH, "--line", str(line), "--rule", "o20-is-company",
                "--match", '"is_company"', "--body", RULE_BODY]
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, self.ENV), \
                mock.patch.object(inline.subprocess, "run", gh), mock.patch("builtins.print"):
            return inline.main()

    def test_posts_once_then_finds_its_thread(self):
        gh = FakeGh(ADDS, [])
        self.assertEqual(self.run_main(gh), 0)
        self.assertEqual(len(gh.posted), 1)
        body = next(a for a in gh.posted[0] if a.startswith("body="))[len("body="):]
        self.assertIn("<!-- argus:rule=o20-is-company;line=", body)
        self.assertIn("commit_id=abc123", gh.posted[0])
        # The next push: the same rule on the same unchanged line is not posted again.
        again = FakeGh(ADDS, [comment(7, body)])
        self.assertEqual(self.run_main(again), 0)
        self.assertEqual(again.posted, [])

    def test_refuses_when_the_pr_only_removes(self):
        gh = FakeGh(REMOVES, [])
        self.assertEqual(self.run_main(gh, line=13), 1)
        self.assertEqual(gh.posted, [])


if __name__ == "__main__":
    unittest.main()
