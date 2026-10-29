#!/usr/bin/env python3
"""The only way Argus may comment on a line of the PR: it checks the anchor, then posts.

Argus had the action's inline comment tool, which posts wherever it is told. On
l10n_ro_ent#1005 the rule "is_company is computed on 20.0" landed again and again on a
docstring next to lines the PR only removed. This script refuses such comments:

- the line (or the range --start..--line) must be on the right side of the diff;
- --match, the code the comment is about, must be on a line the PR adds inside the range
  (with --context, also on a context line next to an added one): a pattern the PR only
  removes is not a finding, and a comment cannot land on an unrelated line;
- a comment is not posted again when a thread (resolved or not) of Argus or Mentor already
  has the same rule on the same file and the line it points at has not changed since.

Usage (PR_NUMBER, HEAD_SHA and REPO come from the job):
    .argus/inline.py --path <file> --line <n> [--start <n>] --rule <slug> --match <code> [--context] --body '<text>'
Exit 0: posted, or already there (the thread is named). Exit 1: refused, with the reason.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

BOTS = ("argus-terrabit[bot]", "mentor-terrabit[bot]")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
MARKER = re.compile(r"<!-- argus:rule=([\w.-]+);line=([0-9a-f]+) -->")
SLUG = re.compile(r"^[\w.-]+$")
# Context lines this far from an added line still count as the added line's context.
NEAR = 3


def parse_patch(patch: str) -> dict:
    """The right side of a file's patch: {"added": {n: text}, "context": {n: text}, "removed": [text]}."""
    added, context, removed = {}, {}, []
    line = None
    for raw in (patch or "").split("\n"):
        m = HUNK.match(raw)
        if m:
            line = int(m.group(1))
            continue
        if line is None or not raw or raw.startswith("\\"):
            continue
        if raw.startswith("+"):
            added[line] = raw[1:]
            line += 1
        elif raw.startswith("-"):
            removed.append(raw[1:])
        else:
            context[line] = raw[1:]
            line += 1
    return {"added": added, "context": context, "removed": removed}


def added_matches(side: dict, fragment: str) -> list[int]:
    """The added lines that hold `fragment`: the findings of a pattern rule on this file."""
    return sorted(n for n, text in side["added"].items() if fragment in text)


def near_added(side: dict, n: int) -> bool:
    return n in side["added"] or any(abs(n - a) <= NEAR for a in side["added"])


def check_anchor(side: dict | None, start: int, line: int, fragment: str, context: bool = False) -> str | None:
    """None if the comment may go on start..line, else why not.

    `fragment` must be on a line the PR adds inside the range; with `context`, also on a
    context line next to an added one (an unchanged call the change breaks), never next to
    lines the PR only removes.
    """
    if side is None:
        return "fișierul nu e în diff-ul PR-ului (sau GitHub nu-i dă patch-ul)."
    if start > line:
        return f"--start {start} e după --line {line}."
    if not fragment.strip():
        return "--match e gol: pune codul pe care îl semnalezi, așa cum apare pe linie."
    span = range(start, line + 1)
    right = side["added"].keys() | side["context"].keys()
    outside = [n for n in span if n not in right]
    if outside:
        return (f"liniile {', '.join(map(str, outside))} nu sunt în partea dreaptă a diff-ului "
                "(linii șterse sau în afara hunk-urilor).")
    if not side["added"]:
        return "PR-ul doar șterge linii din acest fișier: nu e nimic adăugat de comentat."
    hits = added_matches(side, fragment)
    if any(n in span for n in hits):
        return None
    if context and any(fragment in side["context"].get(n, "") and near_added(side, n) for n in span):
        return None
    if hits:
        where = f" Apare pe liniile adăugate {', '.join(map(str, hits))}: ancorează acolo."
    elif any(fragment in t for t in side["removed"]):
        where = " PR-ul doar îl șterge: nu e o constatare."
    else:
        where = " PR-ul nu-l adaugă nicăieri în fișier."
    kind = "adăugată sau de context lângă una adăugată" if context else "adăugată"
    return f"`{fragment}` nu e pe nicio linie {kind} din intervalul {start}-{line}.{where}"


def line_hash(side: dict, start: int, line: int) -> str:
    """What the comment points at, so a changed line can be commented again."""
    text = "\n".join((side["added"].get(n) or side["context"].get(n) or "").strip()
                     for n in range(start, line + 1))
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def marker(rule: str, digest: str) -> str:
    return f"<!-- argus:rule={rule};line={digest} -->"


def headline(body: str) -> str:
    return " ".join(MARKER.sub("", body or "").strip().split("\n", 1)[0].split())


def find_duplicate(comments: list, path: str, rule: str, digest: str, body: str) -> dict | None:
    """The thread that already says this, if any: same bot rule on the same file and line content.

    Threads posted before the marker existed are matched on their first line, on the same file.
    """
    first = headline(body)
    for c in comments:
        if c.get("in_reply_to_id") or (c.get("user") or {}).get("login") not in BOTS or c.get("path") != path:
            continue
        m = MARKER.search(c.get("body") or "")
        if m:
            if m.group(1) == rule and m.group(2) == digest:
                return c
        elif first and headline(c.get("body")) == first:
            return c
    return None


def gh_lines(*args: str) -> list:
    out = subprocess.run(["gh", "api", "--paginate", *args], capture_output=True, text=True, check=True).stdout
    return [json.loads(row) for row in out.splitlines() if row.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", required=True)
    parser.add_argument("--line", type=int, required=True)
    parser.add_argument("--start", type=int)
    parser.add_argument("--rule", required=True, help="the rule, as a short slug, e.g. o20-is-company")
    parser.add_argument("--match", required=True,
                        help="the code the comment is about, as on the line; it must be on an added line of the range")
    parser.add_argument("--context", action="store_true",
                        help="--match may also be on a context line next to an added one (not for pattern rules)")
    parser.add_argument("--body", required=True)
    args = parser.parse_args()
    if not SLUG.match(args.rule):
        sys.exit("--rule: doar litere, cifre, `.`, `_` și `-`.")
    repo, number = os.environ["REPO"], os.environ["PR_NUMBER"]
    head = os.environ["HEAD_SHA"]
    start = args.start or args.line

    files = gh_lines(f"repos/{repo}/pulls/{number}/files", "--jq", ".[] | {filename, patch} | tojson")
    patch = next((f.get("patch") for f in files if f["filename"] == args.path), None)
    side = parse_patch(patch) if patch is not None else None
    reason = check_anchor(side, start, args.line, args.match, args.context)
    if reason:
        print(f"Refuzat, nepostat: {reason}")
        return 1

    digest = line_hash(side, start, args.line)
    comments = gh_lines(f"repos/{repo}/pulls/{number}/comments",
                        "--jq", ".[] | {id, path, body, in_reply_to_id, html_url, user: {login: .user.login}} | tojson")
    dup = find_duplicate(comments, args.path, args.rule, digest, args.body)
    if dup:
        print(f"Deja comentat, nepostat din nou: {dup.get('html_url') or dup['id']}")
        return 0

    fields = ["-f", f"body={args.body.rstrip()}\n\n{marker(args.rule, digest)}", "-f", f"commit_id={head}",
              "-f", f"path={args.path}", "-F", f"line={args.line}", "-f", "side=RIGHT"]
    if start != args.line:
        fields += ["-F", f"start_line={start}", "-f", "start_side=RIGHT"]
    subprocess.run(["gh", "api", "-X", "POST", f"repos/{repo}/pulls/{number}/comments", "--silent", *fields],
                   check=True)
    print(f"Postat pe {args.path}:{start}-{args.line} ({args.rule}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
