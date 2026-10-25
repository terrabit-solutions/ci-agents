#!/usr/bin/env python3
"""Pune fișele scrise de Mentor ca un singur commit pe ramura PR-ului, prin API-ul GitHub.

Commit-ul e semnat de aplicația Mentor Terrabit (tokenul ei, în MENTOR_TOKEN). Ramura
doar avansează. Peste commit-urile Mentor apărute între timp (capturile, din jobul
paralel; alte căi) se pune deasupra, cu reîncercare dacă ramura se mișcă; dacă
programatorul a împins între timp, fișa nu se pune: rularea push-ului nou o reface.

Folosire (din rădăcina repo-ului suitei):
    python3 push_commit.py <owner/repo> <ramura> <head_sha> <raport.json> <verificare.json>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
BOT = "mentor-terrabit[bot]"


class ApiError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def api(method: str, path: str, data: dict | None = None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(data).encode() if data else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {os.environ['MENTOR_TOKEN']}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        raise ApiError(err.code, f"GitHub {err.code} on {method} {path}: {err.read().decode()[:300]}") from None


def only_mentor_since(repo: str, tested: str, current: str) -> bool:
    """The branch head is the tested commit, or only Mentor committed on top of it."""
    if current == tested:
        return True
    cmp = api("GET", f"/repos/{repo}/compare/{tested}...{current}")
    return cmp["status"] == "ahead" and all((c.get("author") or {}).get("login") == BOT for c in cmp["commits"])


def main() -> None:
    repo, branch, head, report_path, verify_path = sys.argv[1:6]
    changed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "*/readme/FISA_CONSULTANT.md"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    # Only the sheets of the modules Mentor was given, whatever else changed.
    selected = {m["module"] for m in json.load(open(".mentor-modules.json", encoding="utf-8"))}
    files = [line[3:] for line in changed if line[3:].split("/", 1)[0] in selected]
    if not files:
        print("Mentor n-a schimbat nicio fișă.")
        return
    def load(path: str) -> list:
        try:
            return json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            return []

    report = {r.get("module"): r for r in load(report_path)}
    verify = {v.get("module"): v for v in load(verify_path)}

    tree = [{"path": f, "mode": "100644", "type": "blob",
             "content": open(f, encoding="utf-8").read()} for f in files]

    modules = [f.split("/", 1)[0] for f in files]
    lines = [f"[DOC] {', '.join(modules)}: fișa consultant (Mentor)", ""]
    for module in modules:
        r, v = report.get(module, {}), verify.get(module)
        status = "făcută" if r.get("action") == "create" else "actualizată"
        verdict = v.get("verdict", "?") if v else "NEVERIFICATĂ (verificatorul n-a raportat)"
        lines.append(f"- {module}: fișă {status}; verificare: {verdict}")
        for f in (v or {}).get("findings", []):
            if f.get("severity") in ("critic", "major"):
                lines.append(f"  - rămas deschis ({f['severity']}): {f.get('text', '')}")
        if r.get("screenshots"):
            lines.append(f"  - capturi de refăcut: {', '.join(r['screenshots'])}")
    for _attempt in range(3):
        current = api("GET", f"/repos/{repo}/git/ref/heads/{branch}")["object"]["sha"]
        if not only_mentor_since(repo, head, current):
            print(f"{branch} moved past the reviewed commit {head[:9]}: the sheet is not committed.")
            return
        base_tree = api("GET", f"/repos/{repo}/git/commits/{current}")["tree"]["sha"]
        new_tree = api("POST", f"/repos/{repo}/git/trees", {"base_tree": base_tree, "tree": tree})
        commit = api("POST", f"/repos/{repo}/git/commits",
                     {"message": "\n".join(lines) + "\n", "tree": new_tree["sha"], "parents": [current]})
        try:
            api("PATCH", f"/repos/{repo}/git/refs/heads/{branch}", {"sha": commit["sha"], "force": False})
        except ApiError as err:
            # 422: not a fast-forward, the branch moved; anything else will not improve.
            if err.code != 422:
                raise
            print(f"The branch moved ({err}); retrying.")
            if _attempt < 2:
                time.sleep(5)
            continue
        print(f"Commit {commit['sha'][:9]} on {branch}: {', '.join(files)}")
        return
    sys.exit("Could not commit the sheet after 3 attempts.")


if __name__ == "__main__":
    try:
        main()
    except ApiError as err:
        sys.exit(str(err))
