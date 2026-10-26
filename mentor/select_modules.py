#!/usr/bin/env python3
"""Alege modulele din PR a căror fișă consultant trebuie făcută sau actualizată.

Un modul intră în listă dacă PR-ul îi schimbă funcțional codul (modele, view-uri,
wizard-uri, date, rapoarte, meniuri, manifest, readme DESCRIPTION/USAGE/CONFIGURE)
după ultimul commit în care Mentor i-a scris fișa în același PR. Schimbările doar
în teste, traduceri, capturi, istoric sau README-uri generate nu contează.

Cu `--screenshots`, alege în schimb modulele cu `tests/test_screenshots.py` ale căror capturi pot
arăta altfel, după ultimul commit în care Mentor le-a pus capturile: un XML de ecran schimbat (view-uri,
wizard-uri, șabloane OWL din `static/src/`), testul de capturi schimbat (ecrane noi), sau fișa cu
pași noi, adică trimiteri la capturi care nu erau în ramura de bază ori lipsesc din modul. Celelalte
schimbări (modele, date, securitate, manifest, readme) nu refac capturile. Fără AI: le face testul.

Folosire (din rădăcina repo-ului suitei):
    python3 mentor/select_modules.py <base_sha> <head_sha> <bot_login> [--limit 2] [--screenshots]
Scrie JSON pe stdout: {"selected": [{"module", "action", "reason"}], "skipped": [...]}.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

FUNCTIONAL = ("models/", "views/", "wizard/", "wizards/", "data/", "report/", "reports/",
              "security/", "controllers/", "static/src/")
FUNCTIONAL_FILES = ("__manifest__.py", "readme/DESCRIPTION.md", "readme/USAGE.md", "readme/CONFIGURE.md")
FISA = "readme/FISA_CONSULTANT.md"
SHOTS = ("static/description/", "readme/screenshots/")
SHOT_TEST = "tests/test_screenshots.py"
SCREEN_XML = ("views/", "wizard/", "wizards/", "static/src/")
SHOT_REF = re.compile(r"\(([^()\s]+\.png)\)")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def is_functional(rel: str) -> bool:
    return rel in FUNCTIONAL_FILES or rel.startswith(FUNCTIONAL)


def changes_screens(rel: str) -> bool:
    """A change that can make a screenshot look different or call for a new one."""
    return rel == SHOT_TEST or (rel.endswith(".xml") and rel.startswith(SCREEN_XML))


def shot_refs(text: str) -> set[str]:
    return {Path(ref).name for ref in SHOT_REF.findall(text)}


def new_steps(base: str, module: str) -> list[str]:
    """Screenshots the sheet refers to that the base branch's sheet did not, or that are missing."""
    path = Path(module, FISA)
    if not path.is_file():
        return []
    head_refs = shot_refs(path.read_text(encoding="utf-8"))
    try:
        base_refs = shot_refs(git("show", f"{base}:{module}/{FISA}"))
    except subprocess.CalledProcessError:
        base_refs = set()
    present = {p.name for d in SHOTS for p in Path(module, d).glob("*.png")}
    return sorted((head_refs - base_refs) | (head_refs - present))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("head")
    ap.add_argument("bot")
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--screenshots", action="store_true")
    args = ap.parse_args()

    # Commit-urile PR-ului, cel mai vechi primul, cu autorul și fișierele atinse.
    log = git("log", "--reverse", "--format=@@%H%x09%an", "--name-only", f"{args.base}..{args.head}")
    last_change: dict[str, int] = {}
    last_fisa_by_bot: dict[str, int] = {}
    order = 0
    author = ""
    for line in log.splitlines():
        if line.startswith("@@"):
            order += 1
            author = line.split("\t", 1)[1]
            continue
        if "/" not in line:
            continue
        module, rel = line.split("/", 1)
        if not Path(module, "__manifest__.py").is_file():
            continue
        mine = rel.startswith(SHOTS) and rel.endswith(".png") if args.screenshots else rel == FISA
        counts = (changes_screens(rel) or rel == FISA) if args.screenshots else is_functional(rel)
        if mine and args.bot in author:
            last_fisa_by_bot[module] = order
        elif counts and args.bot not in author:
            last_change[module] = order

    selected = []
    for module, changed_at in sorted(last_change.items(), key=lambda kv: -kv[1]):
        if last_fisa_by_bot.get(module, 0) > changed_at:
            continue  # fișa (sau capturile) e deja la zi cu ultima schimbare
        if args.screenshots:
            if not Path(module, SHOT_TEST).is_file():
                continue
            # The sheet alone counts only when it has new steps (new or missing screenshots).
            files = git("log", "--format=", "--name-only", f"{args.base}..{args.head}", "--", module).split()
            screens = any(changes_screens(f.split("/", 1)[1]) for f in files if "/" in f)
            steps = new_steps(args.base, module)
            if screens:
                selected.append({"module": module, "action": "screenshots", "reason": "ecrane schimbate în PR"})
            elif steps:
                selected.append({"module": module, "action": "screenshots",
                                 "reason": "pași noi în fișă: " + ", ".join(steps)})
            continue
        exists = Path(module, FISA).is_file()
        selected.append({
            "module": module,
            "action": "update" if exists else "create",
            "reason": "cod schimbat în PR" if exists else "modul fără fișă, schimbat în PR",
        })
    print(json.dumps({"selected": selected[: args.limit], "skipped": [m["module"] for m in selected[args.limit:]]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
