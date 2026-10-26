#!/usr/bin/env python3
"""Duce pe commit-ul Mentor rezultatul rulării care l-a produs.

Push-urile Mentor (fișa, capturile) nu reiau joburile Mentor, ca să nu intre în buclă, așa că
rularea de pe commit-ul lor ar ieși verde (sărită) chiar dacă rularea care le-a făcut a picat,
de exemplu la capturi. Scriptul coboară din capul PR-ului peste commit-urile Mentor până la
commit-ul programatorului, găsește rularea Mentor de pe el și pică dacă acolo au picat
fișa, capturile, commit-ul lor sau verificarea fișei.

Folosire (în jobul carry din mentor.yml; GH_TOKEN, HEAD, BRANCH, WORKFLOW_REF din env):
    python3 -I carry_result.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://api.github.com"
BOT = "mentor-terrabit[bot]"
# The jobs whose failure the PR must show, in their order (sheet, screenshots, check); one still
# running when this job starts counts as passed (each pushes before its last steps).
JOBS = ("sheet", "screenshots", "screenshots-commit", "sheet-check")
OK = ("success", "skipped", None)


def get(path: str):
    req = urllib.request.Request(API + path)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {os.environ['GH_TOKEN']}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def author_commit(repo: str, sha: str) -> str:
    """The first commit below `sha` (itself included) that Mentor did not make."""
    for _ in range(20):
        commit = get(f"/repos/{repo}/commits/{sha}")
        if (commit.get("author") or {}).get("login") != BOT or not commit["parents"]:
            return sha
        sha = commit["parents"][0]["sha"]
    raise SystemExit(f"::error::More than 20 Mentor commits on top of each other below {os.environ['HEAD']}.")


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = author_commit(repo, os.environ["HEAD"])
    branch = urllib.parse.quote(os.environ["BRANCH"], safe="")
    workflow = os.environ["WORKFLOW_REF"].split("@")[0].rsplit("/", 1)[-1]
    runs = get(f"/repos/{repo}/actions/workflows/{workflow}/runs?branch={branch}&head_sha={sha}&per_page=20")
    for run in runs["workflow_runs"]:
        # Called jobs are named "<caller job> / <job>"; the latest attempt of each.
        jobs = {j["name"].rsplit(" / ", 1)[-1]: j["conclusion"]
                for j in get(f"/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]}
        if any(jobs.get(name) not in ("skipped", None) for name in JOBS) or run["status"] != "completed":
            break
    else:
        print(f"No Mentor run found for {sha}: nothing to carry.")
        return
    failed = [name for name in JOBS if jobs.get(name) not in OK]
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not failed:
        text = f"Rularea Mentor de pe `{sha[:8]}` ({run['html_url']}) a trecut."
        print(text)
    else:
        text = (f"Rularea Mentor de pe `{sha[:8]}`, care a făcut acest commit, a picat la "
                f"`{', '.join(failed)}`: {run['html_url']}. Reia joburile picate acolo, apoi acest job.")
        print(f"::error::Mentor run for {sha[:8]} failed at {', '.join(failed)}: {run['html_url']}")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"## Mentor\n\n{text}\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
