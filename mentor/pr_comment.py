#!/usr/bin/env python3
"""Pune raportul rulării Mentor ca un singur comentariu pe PR, editat la fiecare rulare.

Mesajele commit-urilor Mentor păstrează doar rezumatul; aici intră tot: verdictul și
constatările verificatorului pe fiecare modul, capturile regenerate (cu miniaturi) și
starea rulării. Comentariul e găsit după markerul ascuns MARKER și rescris, ca să nu
se adune câte unul la fiecare push. O rulare fără nimic de făcut nu deschide comentariu,
doar îl actualizează pe cel existent.

Comentariul e scris de aplicația Mentor Terrabit (tokenul ei, în MENTOR_TOKEN, cu
Pull requests: write).

Folosire (din rădăcina repo-ului suitei, după jobul sheet):
    python3 pr_comment.py <owner/repo> <nr_pr> <ramura> <sha_pr> <raport.json> <verificare.json>
Mediu: SCREENSHOTS (rezultatul jobului screenshots), SHOTS_COMMIT (al jobului
screenshots-commit), RUN_URL. Cu MODE=review (jobul review) raportul e `.mentor-precheck.json`
(`sheet` spune dacă modulul are fișă) și comentariul spune ce lipsește din fișe, nu ce s-a refăcut.
În modul review raportul e un review pe push-ul verificat, ca la Argus: Mentor apare la Reviewers
și la fiecare push, chiar și când n-are nimic de verificat. Aprobă (APPROVE) când fiecare modul
are fișa și rularea le-a verificat pe toate fără constatări critice sau majore (JOB_OK=true: niciun
pas al jobului n-a eșuat), cere modificări (REQUEST_CHANGES) la o constatare critică sau majoră
(acelea care pică check-ul `mentor / review`) și doar comentează în rest. Un review pe același push și cu același verdict e rescris, nu dublat;
aprobările și cererile de modificări Mentor mai vechi sunt retrase (dismiss).
"""
from __future__ import annotations

import fnmatch
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
BOT = "mentor-terrabit[bot]"
MARKER = "<!-- mentor-report -->"
SEVERITY = {"critic": "🔴", "major": "🟠", "minor": "🟡", "observație": "🔵"}
# Thumbnails beyond this go as a plain list: a comment is not a gallery.
MAX_THUMBS = 12


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


def load(path: str) -> list:
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def mentor_changes(repo: str, pr_sha: str, branch: str) -> tuple[str, list[str] | None]:
    """The branch head now and the files Mentor committed on top of the pushed head.

    Through the API: the sheet commit is made by the API too and is not in the checkout.
    """
    head = api("GET", f"/repos/{repo}/git/ref/heads/{urllib.parse.quote(branch, safe='')}")["object"]["sha"]
    if head == pr_sha:
        return head, []
    cmp = api("GET", f"/repos/{repo}/compare/{pr_sha}...{head}")
    if cmp["status"] != "ahead" or any((c.get("author") or {}).get("login") != BOT for c in cmp["commits"]):
        # The author pushed again: that push's run writes the comment.
        return head, None
    return head, [f["filename"] for f in cmp.get("files") or [] if f.get("status") != "removed"]


def find_comment(repo: str, number: str) -> dict | None:
    page = 1
    while True:
        comments = api("GET", f"/repos/{repo}/issues/{number}/comments?per_page=100&page={page}")
        for comment in comments:
            if MARKER in (comment.get("body") or ""):
                return comment
        if len(comments) < 100:
            return None
        page += 1


def build(repo: str, pr_sha: str, head: str, report: list, verify: list,
          sheets: list[str], shots: list[str]) -> tuple[str, bool]:
    """The comment body, and whether there is anything to report at all."""
    screenshots = os.environ.get("SCREENSHOTS", "")
    shots_commit = os.environ.get("SHOTS_COMMIT", "")
    run_url = os.environ.get("RUN_URL", "")
    review = os.environ.get("MODE") == "review"
    reports = {r.get("module"): r for r in report if isinstance(r, dict)}
    verifies = {v.get("module"): v for v in verify if isinstance(v, dict)}
    sheet_modules = {f.split("/", 1)[0] for f in sheets}
    modules = sorted(set(reports) | set(verifies) | sheet_modules | {f.split("/", 1)[0] for f in shots})

    lines = [MARKER, "## Mentor review" if review else "## Mentor", ""]
    serious = 0
    for module in modules:
        r, v = reports.get(module, {}), verifies.get(module)
        if review:
            status = "fișă verificată" if r.get("sheet") else "fișă lipsă"
        elif module in sheet_modules:
            status = "fișă făcută" if r.get("action") == "create" else "fișă actualizată"
        elif r or v:
            status = "fișă neschimbată"
        else:
            status = "doar capturi"
        lines.append(f"### `{module}`: {status}")
        lines.append("")
        if v:
            lines.append(f"**Verificare:** {v.get('verdict') or '?'}")
            findings = v.get("findings") or []
            if findings:
                lines.append("")
                for f in findings:
                    sev = f.get("severity", "")
                    serious += sev in ("critic", "major")
                    lines.append(f"- {SEVERITY.get(sev, '•')} **{sev or '?'}**: {f.get('text', '')}")
            lines.append("")
        elif module in sheet_modules:
            lines += ["**Verificare:** NEVERIFICATĂ (verificatorul n-a raportat)", ""]
        todo = r.get("screenshots") or []
        if todo:
            lines += [f"Capturi cerute de fișă: {', '.join(f'`{s}`' for s in todo)}", ""]
        mod_shots = [f for f in shots if f.split("/", 1)[0] == module]
        if mod_shots:
            lines.append(f"<details><summary>Capturi regenerate ({len(mod_shots)})</summary>")
            lines.append("")
            for path in mod_shots[:MAX_THUMBS]:
                url = f"https://github.com/{repo}/blob/{head}/{urllib.parse.quote(path)}?raw=true"
                name = path.rsplit("/", 1)[-1]
                lines.append(f'<a href="{url}"><img src="{url}" width="260" alt="{name}" title="{name}"></a>')
            rest = mod_shots[MAX_THUMBS:]
            if rest:
                lines += ["", "Și: " + ", ".join(f"`{p.rsplit('/', 1)[-1]}`" for p in rest)]
            lines += ["", "</details>", ""]

    failed = [name for name, result in (("capturile", screenshots), ("commit-ul capturilor", shots_commit))
              if result in ("failure", "cancelled")]
    if failed:
        lines += [f"⚠️ Au eșuat: {', '.join(failed)}. Detalii în [rulare]({run_url}).", ""]
    if not modules and not failed:
        lines += [f"Nimic de verificat la `{pr_sha[:9]}`: PR-ul nu schimbă funcțional niciun modul." if review
                  else f"Nimic de refăcut la `{pr_sha[:9]}`: fișele și capturile urmează deja codul.", ""]
    elif serious and review:
        lines += [f"Rămân **{serious}** constatări critice sau majore: check-ul `mentor / review` pică "
                  "și nu vine `mentor-ok`. Fișa se face sau se completează local cu Mentor (`fisa-completa`), cu capturile, "
                  "și se împinge în PR.", ""]
    elif serious:
        lines += [f"Rămân **{serious}** constatări critice sau majore: fără `mentor-ok`, merge manual.", ""]
    elif not failed:
        lines += ["Fără constatări critice sau majore.", ""]
    after = "" if review else f" · ramura după Mentor: `{head[:9]}`"
    lines.append(f"<sub>Rularea: [{run_url.rsplit('/', 1)[-1] or 'Actions'}]({run_url}) · "
                 f"push-ul verificat: `{pr_sha[:9]}`{after}</sub>")
    return "\n".join(lines) + "\n", bool(modules or failed)


def mentor_reviews(repo: str, number: str) -> list[dict]:
    reviews, page = [], 1
    while True:
        batch = api("GET", f"/repos/{repo}/pulls/{number}/reviews?per_page=100&page={page}")
        reviews += [r for r in batch if (r.get("user") or {}).get("login") == BOT
                    and MARKER in (r.get("body") or "")]
        if len(batch) < 100:
            return reviews
        page += 1


def review_event(report: list, verify: list, job_ok: bool) -> str:
    """REQUEST_CHANGES on a critical or major finding (those fail the `mentor / review` check);
    APPROVE when every module has its sheet, the run checked all of them and nothing critical or
    major is left; COMMENT otherwise (nothing to check, a module the check did not reach, a
    failed step)."""
    modules = {r.get("module"): r for r in report if isinstance(r, dict)}
    verifies = {v.get("module"): v for v in verify if isinstance(v, dict)}
    severities = [f.get("severity") for v in verifies.values() for f in v.get("findings") or []]
    if {"critic", "major"} & set(severities):
        return "REQUEST_CHANGES"
    if job_ok and modules \
            and all(r.get("sheet") and m in verifies for m, r in modules.items()):
        return "APPROVE"
    return "COMMENT"


# The state GitHub gives a review submitted with each event.
STATE = {"APPROVE": "APPROVED", "REQUEST_CHANGES": "CHANGES_REQUESTED", "COMMENT": "COMMENTED"}


def post_review(repo: str, number: str, pr_sha: str, report_path: str, verify_path: str) -> None:
    """The review job: Mentor commits nothing, so the branch is not read (the token has no
    Contents permission); the report goes as a review on the pushed head, with the event of
    review_event. A review of the same push and verdict is rewritten, not doubled; Mentor's
    earlier approvals and change requests that no longer hold are dismissed, so the PR shows
    only the verdict of the last push."""
    report, verify = load(report_path), load(verify_path)
    body, _anything = build(repo, pr_sha, pr_sha, report, verify, [], [])
    event = review_event(report, verify, os.environ.get("JOB_OK") == "true")
    reviews = mentor_reviews(repo, number)
    keep = next((r for r in reviews if r.get("commit_id") == pr_sha and r.get("state") == STATE[event]), None)
    for old in reviews:
        if old is not keep and old.get("state") in ("APPROVED", "CHANGES_REQUESTED"):
            api("PUT", f"/repos/{repo}/pulls/{number}/reviews/{old['id']}/dismissals",
                {"message": f"Înlocuit de verificarea Mentor a push-ului {pr_sha[:9]}.", "event": "DISMISS"})
    if keep:
        api("PUT", f"/repos/{repo}/pulls/{number}/reviews/{keep['id']}", {"body": body})
        print(f"Review-ul Mentor ({event}) actualizat: {keep['html_url']}")
    else:
        created = api("POST", f"/repos/{repo}/pulls/{number}/reviews",
                      {"commit_id": pr_sha, "event": event, "body": body})
        print(f"Review-ul Mentor ({event}) adăugat: {created['html_url']}")


def main() -> None:
    repo, number, branch, pr_sha, report_path, verify_path = sys.argv[1:7]
    if os.environ.get("MODE") == "review":
        post_review(repo, number, pr_sha, report_path, verify_path)
        return
    head, files = mentor_changes(repo, pr_sha, branch)
    if files is None:
        print(f"{branch} moved past {pr_sha[:9]}: the next run writes the comment.")
        return
    sheets = [f for f in files if fnmatch.fnmatch(f, "*/readme/FISA_CONSULTANT.md")]
    shots = [f for f in files if f.endswith(".png")]
    body, anything = build(repo, pr_sha, head, load(report_path), load(verify_path), sheets, shots)
    existing = find_comment(repo, number)
    if existing:
        api("PATCH", f"/repos/{repo}/issues/comments/{existing['id']}", {"body": body})
        print(f"Comentariul Mentor actualizat: {existing['html_url']}")
    elif anything:
        created = api("POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})
        print(f"Comentariul Mentor adăugat: {created['html_url']}")
    else:
        print("Nimic de raportat: fără comentariu.")


if __name__ == "__main__":
    try:
        main()
    except ApiError as err:
        sys.exit(str(err))
