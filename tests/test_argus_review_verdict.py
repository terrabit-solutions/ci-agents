"""Tests of argus/review_verdict.py: the review Argus submits and the dismissal of its
earlier verdicts.

Run from the repository root: python3 -m unittest discover -s tests
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "argus"))

import review_verdict  # noqa: E402

SHA = "ee076f6b69e3f7f9b2e129ba13fc871b9ebfe87e"
DISMISS = "/repos/o/r/pulls/1/reviews/{}/dismissals"


def review(rid: int, state: str, sha: str = SHA, login: str = review_verdict.BOT) -> dict:
    return {"id": rid, "state": state, "commit_id": sha, "html_url": "u", "user": {"login": login}}


class TestReviewVerdict(unittest.TestCase):
    def run_verdict(self, event: str, reviews: list[dict], blocking: str = "0") -> list[tuple]:
        calls = []

        def api(method, path, data=None):
            calls.append((method, path, data))
            if method == "GET":
                return reviews
            return {"html_url": "https://x/review"}

        argv = ["review_verdict.py", "o/r", "1", SHA, event, blocking]
        with mock.patch.object(review_verdict, "api", api), mock.patch.object(sys, "argv", argv), \
                mock.patch("builtins.print"):
            review_verdict.main()
        return [c for c in calls if c[0] != "GET"]

    def test_clean_head_approves(self):
        calls = self.run_verdict("APPROVE", [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2]["event"], "APPROVE")
        self.assertEqual(calls[0][2]["commit_id"], SHA)

    def test_blocking_requests_changes_and_dismisses_old_approval(self):
        calls = self.run_verdict("REQUEST_CHANGES", [review(5, "APPROVED", sha="old")], blocking="2")
        self.assertEqual(calls[0][:2], ("PUT", DISMISS.format(5)))
        self.assertEqual(calls[1][2]["event"], "REQUEST_CHANGES")
        self.assertIn("**2**", calls[1][2]["body"])

    def test_important_only_dismisses_and_adds_no_review(self):
        calls = self.run_verdict("COMMENT", [review(5, "CHANGES_REQUESTED", sha="old")])
        self.assertEqual(calls, [("PUT", DISMISS.format(5), calls[0][2])])

    def test_same_head_same_verdict_is_kept(self):
        self.assertEqual(self.run_verdict("APPROVE", [review(5, "APPROVED")]), [])

    def test_other_reviewers_and_comments_are_left_alone(self):
        reviews = [review(5, "APPROVED", login="dhongu"), review(6, "COMMENTED", sha="old")]
        # The GET returns them all; only Argus's approvals and change requests are dismissed.
        calls = self.run_verdict("APPROVE", reviews)
        self.assertEqual([c[0] for c in calls], ["POST"])


if __name__ == "__main__":
    unittest.main()
