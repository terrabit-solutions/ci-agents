#!/usr/bin/env python3
"""Unește un PR al unei suite când e gata: eticheta automerge, Argus și Mentor curați, nimic în lucru.

Rulează după fiecare workflow terminat pe un PR (teste, Argus, Mentor) și când se pune o etichetă.
Fără AI: decide doar din starea PR-ului pe GitHub. PR-ul se unește dacă, pe ultimul commit:

- e deschis, nu e draft, are `automerge` și `argus-ok`, plus `mentor-ok` (în afară de `mentor-skip`);
- n-are `wip`, `needs-pacioli` sau `no-merge`;
- ultimul review Argus e pe ultimul commit care nu e al lui Mentor (un push sărit de Argus nu trece);
- nu mai rulează nimic pe ramura PR-ului, iar toate rulările de pe ultimul commit au trecut;
- GitHub îl dă ca unibil fără conflicte.

Citirile se fac cu GITHUB_TOKEN (READ_TOKEN), merge-ul cu tokenul aplicației Argus (MERGE_TOKEN),
legat de commit-ul verificat, ca un push venit între timp să nu fie unit nevăzut.

Folosire: python3 decide.py <owner/repo> <număr PR> [<număr PR> ...]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
ARGUS = "argus-terrabit[bot]"
MENTOR = "mentor-terrabit[bot]"
STOP = {"wip", "needs-pacioli", "no-merge"}
PASSED = {"success", "skipped", "neutral"}


def api(method: str, path: str, token: str, data: dict | None = None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(data).encode() if data else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read() or b"null")


def pages(path: str, token: str, key: str | None = None):
    sep = "&" if "?" in path else "?"
    page = 1
    while True:
        batch = api("GET", f"{path}{sep}per_page=100&page={page}", token)
        items = batch[key] if key else batch
        yield from items
        if len(items) < 100:
            return
        page += 1


def is_automerge(run: dict) -> bool:
    return str(run["id"]) == os.environ.get("GITHUB_RUN_ID") or run.get("path", "").endswith("/automerge.yml")


def why_not(repo: str, number: int, read: str) -> tuple[str | None, dict]:
    pr = api("GET", f"/repos/{repo}/pulls/{number}", read)
    labels = {lab["name"].lower() for lab in pr["labels"]}
    if pr["state"] != "open":
        return "nu e deschis", pr
    if "automerge" not in labels:
        return "n-are eticheta automerge", pr
    if pr["draft"]:
        return "e draft", pr
    if labels & STOP:
        return "are " + ", ".join(sorted(labels & STOP)), pr
    if "argus-ok" not in labels:
        return "n-are argus-ok", pr
    if "mentor-ok" not in labels and "mentor-skip" not in labels:
        return "n-are mentor-ok", pr
    head, branch = pr["head"]["sha"], pr["head"]["ref"]

    # Argus must have reviewed the last commit that is not Mentor's own.
    commits = list(pages(f"/repos/{repo}/pulls/{number}/commits", read))
    authored = [c["sha"] for c in commits if (c.get("author") or {}).get("login") != MENTOR]
    reviews = [r for r in pages(f"/repos/{repo}/pulls/{number}/reviews", read) if r["user"]["login"] == ARGUS]
    if not authored or not reviews or reviews[-1]["commit_id"] != authored[-1]:
        return "ultimul commit al autorului n-are review Argus", pr

    # Nothing still running on the PR's branch (the sheet of an earlier head, tests, ...);
    # this workflow's own runs aside.
    branch_q = urllib.parse.quote(branch, safe="")
    for status in ("queued", "in_progress", "waiting", "pending", "requested"):
        for run in pages(f"/repos/{repo}/actions/runs?branch={branch_q}&status={status}", read, "workflow_runs"):
            if not is_automerge(run):
                return f"rulează încă {run['name']} ({run['id']})", pr

    # On the head, the last run of each workflow passed (an earlier one may have been
    # cancelled by a newer run of the same workflow, as at "Ready for review").
    last = {}
    for run in pages(f"/repos/{repo}/actions/runs?head_sha={head}", read, "workflow_runs"):
        if is_automerge(run):
            continue
        if run["workflow_id"] not in last or run["created_at"] > last[run["workflow_id"]]["created_at"]:
            last[run["workflow_id"]] = run
    for run in last.values():
        if run["status"] != "completed":
            return f"rulează încă {run['name']} ({run['id']})", pr
        if run["conclusion"] not in PASSED:
            return f"{run['name']} s-a terminat cu {run['conclusion']} ({run['id']})", pr

    # GitHub computes mergeability lazily: read it again once it is known.
    pr = api("GET", f"/repos/{repo}/pulls/{number}", read)
    if pr["head"]["sha"] != head:
        return "a apărut un commit nou", pr
    if pr.get("mergeable") is not True:
        return f"GitHub nu-l dă unibil ({pr.get('mergeable_state')})", pr
    return None, pr


def main() -> None:
    repo, numbers = sys.argv[1], sys.argv[2:]
    read, merge = os.environ["READ_TOKEN"], os.environ["MERGE_TOKEN"]
    method = os.environ.get("MERGE_METHOD", "merge")
    lines = []
    for number in dict.fromkeys(int(n) for n in numbers):
        reason, pr = why_not(repo, number, read)
        if reason:
            lines.append(f"- #{number}: nu se unește, {reason}.")
            continue
        head = pr["head"]["sha"]
        try:
            api("PUT", f"/repos/{repo}/pulls/{number}/merge", merge, {"merge_method": method, "sha": head})
        except urllib.error.HTTPError as err:
            lines.append(f"- #{number}: GitHub a refuzat merge-ul ({err.code}: {err.read().decode()[:200]}).")
            continue
        api("POST", f"/repos/{repo}/issues/{number}/comments", merge, {"body": (
            f"Merge automat pe `{head[:9]}`: eticheta `automerge`, review Argus curat, fișa și capturile "
            "Mentor curate, toate verificările trecute. Eticheta `no-merge` îl oprește pe un PR viitor.")})
        lines.append(f"- #{number}: unit pe {head[:9]}.")
    text = "## Merge automat\n\n" + ("\n".join(lines) or "Niciun PR de verificat.") + "\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(text)


if __name__ == "__main__":
    main()
