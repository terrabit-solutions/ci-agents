#!/usr/bin/env python3
"""What Argus needs to say whether a PR's change has reached the next Odoo series.

Run by the workflow before the review, without AI: for a PR into 19.0 it looks at 20.0
(18.0 at 19.0 and so on). It writes .argus/next.json and copies the next series' version of
each changed file into .argus-next/<path>, so Argus can compare the two with Read.

    next_version.py <repo> <pr_number> <base_ref> <head_ref>

Advisory: any failure leaves Argus to review as before (the workflow step continues on error).
The fetch uses the git credentials of the environment (GIT_CONFIG_* set by the step).
"""

import json
import re
import subprocess
import sys
from pathlib import Path

OUT = Path(".argus/next.json")
DEST = Path(".argus-next")
CODE = re.compile(r"\.(py|xml|js|scss|csv|po)$")
MAX_FILES = 150


def git(*args, check=True):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def gh_json(*args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout
    return json.loads(out or "null")


def port_prs(repo, number, next_ref, head_ref, base_ref):
    """PRs into the next series that carry this one: the same branch name with the next
    series as prefix (19.0-fix-x -> 20.0-fix-x), or a body naming this PR."""
    twin = head_ref.replace(base_ref, next_ref, 1) if head_ref.startswith(base_ref) else None
    pulls = gh_json(
        "api",
        f"repos/{repo}/pulls?base={next_ref}&state=all&sort=created&direction=desc&per_page=100",
    )
    mention = re.compile(rf"(#|/pull/){number}\b")
    found = []
    for p in pulls or []:
        if p["head"]["ref"] == twin or mention.search(p.get("body") or ""):
            state = "merged" if p.get("merged_at") else p["state"]
            found.append({"number": p["number"], "state": state, "title": p["title"]})
    return found


def main(repo, number, base_ref, head_ref):
    m = re.fullmatch(r"(\d+)\.0", base_ref)
    if not m:
        print(f"Base {base_ref} is not an Odoo series: nothing to check.")
        return
    next_ref = f"{int(m.group(1)) + 1}.0"
    result = {"base": base_ref, "next": next_ref, "branch": False, "port_prs": [], "modules": {}}

    if git("ls-remote", "--exit-code", "--heads", "origin", next_ref, check=False).returncode:
        print(f"No {next_ref} branch: nothing to port to.")
        OUT.write_text(json.dumps(result, indent=1))
        return
    result["branch"] = True
    git("fetch", "-q", "--depth=1", "--no-tags", "--filter=blob:none", "origin", next_ref)
    nxt = git("rev-parse", "FETCH_HEAD").stdout.strip()
    result["next_sha"] = nxt

    files = gh_json(
        "api", "--paginate", f"repos/{repo}/pulls/{number}/files", "--jq", "[.[] | {filename, status}]"
    )
    # --paginate with --jq prints one array per page.
    if files and isinstance(files[0], list):
        files = [f for page in files for f in page]
    copied = 0
    for f in files or []:
        path = f["filename"]
        module = path.split("/", 1)[0]
        if "/" not in path or module.startswith("."):
            continue
        mod = result["modules"].setdefault(
            module,
            {
                "on_next": git("cat-file", "-e", f"{nxt}:{module}/__manifest__.py", check=False).returncode == 0,
                "files": {},
            },
        )
        if not mod["on_next"] or not CODE.search(path) or f["status"] == "added":
            continue
        if git("cat-file", "-e", f"{nxt}:{path}", check=False).returncode:
            mod["files"][path] = "missing"
            continue
        if copied >= MAX_FILES:
            mod["files"][path] = "not copied (limit)"
            continue
        target = DEST / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.run(["git", "show", f"{nxt}:{path}"], capture_output=True, check=True).stdout)
        mod["files"][path] = str(target)
        copied += 1

    try:
        result["port_prs"] = port_prs(repo, number, next_ref, head_ref, base_ref)
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
        result["port_prs_error"] = str(e)[:200]

    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    on_next = sum(m["on_next"] for m in result["modules"].values())
    print(
        f"{next_ref}: {on_next}/{len(result['modules'])} modules exist, {copied} files copied "
        f"to {DEST}/, {len(result['port_prs'])} port PRs."
    )


if __name__ == "__main__":
    main(*sys.argv[1:5])
