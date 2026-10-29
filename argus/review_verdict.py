#!/usr/bin/env python3
"""Argus's verdict as a review on the reviewed head, after the summary comment.

The workflow decides the event from the counts (never Claude): APPROVE on a clean review,
REQUEST_CHANGES on a blocking issue, COMMENT when only important ones are left. A COMMENT
adds no review (the summary is already one); every event dismisses Argus's earlier approvals
and change requests that no longer hold, so the PR shows only the verdict of the last head.
A review of the same head with the same verdict is kept, not doubled.

Usage: review_verdict.py <owner/repo> <pr_number> <head_sha> <APPROVE|REQUEST_CHANGES|COMMENT> <blocking>
Environment: GH_TOKEN, the Argus app token (Pull requests: write).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
BOT = "argus-terrabit[bot]"
# The state GitHub gives a review submitted with each event.
STATE = {"APPROVE": "APPROVED", "REQUEST_CHANGES": "CHANGES_REQUESTED", "COMMENT": "COMMENTED"}


class ApiError(Exception):
    pass


def api(method: str, path: str, data: dict | None = None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(data).encode() if data else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {os.environ['GH_TOKEN']}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        raise ApiError(f"GitHub {err.code} on {method} {path}: {err.read().decode()[:300]}") from None


def argus_verdicts(repo: str, number: str) -> list[dict]:
    """Argus's reviews that weigh on the merge: its approvals and change requests."""
    reviews, page = [], 1
    while True:
        batch = api("GET", f"/repos/{repo}/pulls/{number}/reviews?per_page=100&page={page}")
        reviews += [r for r in batch if (r.get("user") or {}).get("login") == BOT
                    and r.get("state") in ("APPROVED", "CHANGES_REQUESTED")]
        if len(batch) < 100:
            return reviews
        page += 1


def body(event: str, sha: str, blocking: int) -> str:
    if event == "APPROVE":
        return f"Review Argus curat pe `{sha[:9]}`: nimic blocant sau important."
    return (f"Review Argus pe `{sha[:9]}`: **{blocking}** probleme blocante, în comentariile de mai sus. "
            "Se corectează și se împinge în PR; review-ul următor retrage cererea.")


def main() -> None:
    repo, number, sha, event, blocking = sys.argv[1:6]
    if event not in STATE:
        sys.exit(f"unknown event: {event}")
    keep = None
    for old in argus_verdicts(repo, number):
        if keep is None and old.get("commit_id") == sha and old.get("state") == STATE[event]:
            keep = old
            continue
        api("PUT", f"/repos/{repo}/pulls/{number}/reviews/{old['id']}/dismissals",
            {"message": f"Înlocuit de review-ul Argus pe {sha[:9]}.", "event": "DISMISS"})
        print(f"Verdict Argus retras: {old.get('state')} pe {(old.get('commit_id') or '')[:9]}")
    if event == "COMMENT":
        print("Doar probleme importante: rezumatul Argus rămâne singurul review.")
    elif keep:
        print(f"Verdictul Argus ({event}) e deja pe {sha[:9]}: {keep.get('html_url')}")
    else:
        created = api("POST", f"/repos/{repo}/pulls/{number}/reviews",
                      {"commit_id": sha, "event": event, "body": body(event, sha, int(blocking))})
        print(f"Verdict Argus ({event}): {created.get('html_url')}")


if __name__ == "__main__":
    try:
        main()
    except ApiError as err:
        sys.exit(str(err))
