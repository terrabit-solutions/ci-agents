#!/usr/bin/env python3
"""Pune capturile regenerate de testele `fise_screenshots` ca un commit Mentor în PR.

Ia doar capturile care s-au schimbat vizibil: o randare nouă a aceluiași ecran diferă adesea
la nivel de octeți (antialiasing, compresie), fără nicio diferență pe care s-o vadă cineva,
iar un commit la fiecare push ar fi doar zgomot. Bannerul Apps (`main_screenshot.png`) nu
e captură de fișă și rămâne neatins.

Commit-ul se face prin API-ul GitHub, cu tokenul aplicației Mentor (MENTOR_TOKEN), peste
capul curent al ramurii: Mentor poate să fi împins între timp fișa, iar căile nu se suprapun.
Dacă ramura se mișcă în timpul commit-ului, se reîncearcă.

Folosire (din rădăcina repo-ului suitei):
    python3 push_screenshots.py <owner/repo> <ramura> <module.json> <sha-ul testat>
"""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from PIL import Image, ImageChops

API = "https://api.github.com"
SHOT_DIRS = ("static/description/", "readme/screenshots/")
# Number of differing pixels (each by more than 16 levels, which filters the antialiasing
# noise) up to which a new screenshot counts as the same. Absolute, not a share of the
# image: one changed digit of a small font is about 30 pixels of a full screen.
MIN_CHANGED_PIXELS = 10


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


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def visibly_changed(path: str) -> bool:
    """Noua captură diferă de cea din HEAD mai mult decât pragul (sau e nouă)."""
    try:
        old = git("show", f"HEAD:{path}")
    except subprocess.CalledProcessError:
        return True  # captură nouă
    a = Image.open(io.BytesIO(old)).convert("RGB")
    b = Image.open(path).convert("RGB")
    if a.size != b.size:
        return True
    # Largest difference over the three channels: convert("L") would weight blue at 0.11
    # and hide a change of a link or badge colour.
    r, g, bl = ImageChops.difference(a, b).split()
    diff = ImageChops.lighter(ImageChops.lighter(r, g), bl).point(lambda v: 255 if v > 16 else 0)
    changed = sum(1 for v in diff.getdata() if v)
    return changed > MIN_CHANGED_PIXELS


def only_mentor_since(repo: str, tested: str, head: str) -> bool:
    """The branch head is the tested commit, or only Mentor committed on top of it."""
    if head == tested:
        return True
    cmp = api("GET", f"/repos/{repo}/compare/{tested}...{head}")
    return cmp["status"] == "ahead" and all(
        (c.get("author") or {}).get("login") == "mentor-terrabit[bot]" for c in cmp["commits"])


def main() -> None:
    repo, branch, modules_path, tested = sys.argv[1:5]
    modules = {m["module"] for m in json.load(open(modules_path, encoding="utf-8"))}
    # -z: paths unquoted; a deleted screenshot has nothing to upload and is left alone,
    # and a symlink is never followed (it could point anywhere on the runner).
    status = git("status", "--porcelain", "-z", "--untracked-files=all").decode().split("\0")
    candidates = []
    for entry in status:
        path = entry[3:]
        module, _, rel = path.partition("/")
        if module in modules and rel.startswith(SHOT_DIRS) and rel.endswith(".png") \
                and not rel.endswith("main_screenshot.png") \
                and os.path.isfile(path) and not os.path.islink(path):
            candidates.append(path)
    files = [p for p in candidates if visibly_changed(p)]
    unchanged = sorted(set(candidates) - set(files))
    if unchanged:
        print(f"No visible change, left out: {', '.join(unchanged)}")
    if not files:
        print("No screenshot changed visibly.")
        return

    blobs = []
    for path in files:
        content = base64.b64encode(open(path, "rb").read()).decode()
        blob = api("POST", f"/repos/{repo}/git/blobs", {"content": content, "encoding": "base64"})
        blobs.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    by_module: dict[str, list[str]] = {}
    for path in files:
        module, _, rel = path.partition("/")
        by_module.setdefault(module, []).append(rel.rsplit("/", 1)[-1])
    lines = [f"[DOC] {', '.join(sorted(by_module))}: sheet screenshots regenerated (Mentor)", ""]
    lines += [f"- {m}: {', '.join(sorted(names))}" for m, names in sorted(by_module.items())]
    lines += ["", "Generated by the modules' fise_screenshots tests, on the PR code."]

    for attempt in range(3):
        head = api("GET", f"/repos/{repo}/git/ref/heads/{branch}")["object"]["sha"]
        if not only_mentor_since(repo, tested, head):
            # The author pushed after the tested commit: these screenshots may be stale,
            # and on top of the new code they would look up to date. The run for the new
            # push renders them again.
            print(f"{branch} moved past the tested commit {tested[:9]}: screenshots not committed.")
            return
        base_tree = api("GET", f"/repos/{repo}/git/commits/{head}")["tree"]["sha"]
        tree = api("POST", f"/repos/{repo}/git/trees", {"base_tree": base_tree, "tree": blobs})
        commit = api("POST", f"/repos/{repo}/git/commits",
                     {"message": "\n".join(lines) + "\n", "tree": tree["sha"], "parents": [head]})
        try:
            api("PATCH", f"/repos/{repo}/git/refs/heads/{branch}", {"sha": commit["sha"], "force": False})
        except ApiError as err:
            # 422: not a fast-forward, the branch moved. Anything else (401, 403, 404)
            # will not get better with a retry.
            if err.code != 422:
                raise
            print(f"The branch moved ({err}); retrying.")
            time.sleep(5)
            continue
        print(f"Commit {commit['sha'][:9]} on {branch}: {', '.join(files)}")
        return
    sys.exit("Could not commit the screenshots after 3 attempts.")


if __name__ == "__main__":
    main()
