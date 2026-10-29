"""Tests of mentor/pr_comment.py in review mode: the event of Mentor's review and the
dismissal of its earlier verdicts.

Run from the repository root: python3 -m unittest discover -s tests
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mentor"))

import pr_comment  # noqa: E402

SHA = "ee076f6b69e3f7f9b2e129ba13fc871b9ebfe87e"
MODULE = "deltatech_product_attribute_role"


def finding(severity: str) -> dict:
    return {"severity": severity, "text": "..."}


class TestReviewEvent(unittest.TestCase):
    def event(self, sheet=True, findings=(), verified=True, job_ok=True):
        report = [{"module": MODULE, "sheet": sheet}]
        verify = [{"module": MODULE, "verdict": "x", "findings": list(findings)}] if verified else []
        return pr_comment.review_event(report, verify, job_ok)

    def test_sheet_complete_approves(self):
        self.assertEqual(self.event(), "APPROVE")

    def test_minor_findings_still_approve(self):
        self.assertEqual(self.event(findings=[finding("minor"), finding("observație")]), "APPROVE")

    def test_missing_sheet_requests_changes(self):
        # PR 3872: the sheet is missing, a critical finding.
        self.assertEqual(self.event(sheet=False, findings=[finding("critic")]), "REQUEST_CHANGES")

    def test_major_comments(self):
        self.assertEqual(self.event(findings=[finding("major")]), "COMMENT")

    def test_failed_step_does_not_approve(self):
        self.assertEqual(self.event(job_ok=False), "COMMENT")

    def test_module_not_verified_does_not_approve(self):
        self.assertEqual(self.event(verified=False), "COMMENT")

    def test_nothing_to_check_comments(self):
        self.assertEqual(pr_comment.review_event([], [], True), "COMMENT")


class TestPostReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report = os.path.join(self.tmp.name, "precheck.json")
        self.verify = os.path.join(self.tmp.name, "verify.json")
        json.dump([{"module": MODULE, "sheet": True}], open(self.report, "w"))
        json.dump([{"module": MODULE, "verdict": "ok", "findings": []}], open(self.verify, "w"))
        env = {"MODE": "review", "JOB_OK": "true", "RUN_URL": "https://x/runs/1"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_post(self, reviews: list[dict]) -> list[tuple]:
        calls = []

        def api(method, path, data=None):
            calls.append((method, path, data))
            if method == "GET":
                return reviews
            return {"html_url": "https://x/review"}

        with mock.patch.object(pr_comment, "api", api), mock.patch("builtins.print"):
            pr_comment.post_review("o/r", "1", SHA, self.report, self.verify)
        return [c for c in calls if c[0] != "GET"]

    def review(self, rid, state, sha=SHA):
        return {"id": rid, "state": state, "commit_id": sha, "html_url": "u",
                "user": {"login": pr_comment.BOT}, "body": pr_comment.MARKER}

    def test_clean_push_approves_and_dismisses_old_change_request(self):
        calls = self.run_post([self.review(1, "CHANGES_REQUESTED", sha="old")])
        self.assertEqual(calls[0][:2], ("PUT", "/repos/o/r/pulls/1/reviews/1/dismissals"))
        self.assertEqual(calls[1][0], "POST")
        self.assertEqual(calls[1][2]["event"], "APPROVE")

    def test_same_push_same_verdict_rewrites(self):
        calls = self.run_post([self.review(7, "APPROVED")])
        self.assertEqual(calls, [("PUT", "/repos/o/r/pulls/1/reviews/7", calls[0][2])])

    def test_same_push_new_verdict_posts_again(self):
        json.dump([{"module": MODULE, "verdict": "x", "findings": [finding("critic")]}], open(self.verify, "w"))
        calls = self.run_post([self.review(7, "APPROVED"), self.review(8, "COMMENTED", sha="old")])
        self.assertEqual([c[:2] for c in calls],
                         [("PUT", "/repos/o/r/pulls/1/reviews/7/dismissals"),
                          ("POST", "/repos/o/r/pulls/1/reviews")])
        self.assertEqual(calls[1][2]["event"], "REQUEST_CHANGES")


if __name__ == "__main__":
    unittest.main()
