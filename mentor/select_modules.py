#!/usr/bin/env python3
"""Alege modulele din PR a căror fișă consultant trebuie făcută sau actualizată.

Un modul intră în listă dacă PR-ul îi schimbă funcțional codul (modele, view-uri,
wizard-uri, date, rapoarte, meniuri, manifest, readme DESCRIPTION/USAGE/CONFIGURE)
după ultimul commit în care Mentor i-a scris fișa în același PR. Schimbările doar
în teste, traduceri, capturi, istoric sau README-uri generate nu contează.

Cu `--screenshots`, alege în schimb modulele cu `tests/test_screenshots.py` schimbate funcțional
după ultimul commit în care Mentor le-a pus capturile; capturile se refac din test, fără AI.

Folosire (din rădăcina repo-ului suitei):
    python3 mentor/select_modules.py <base_sha> <head_sha> <bot_login> [--limit 2] [--screenshots]
Scrie JSON pe stdout: {"selected": [{"module", "action", "reason"}], "skipped": [...]}.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

FUNCTIONAL = ("models/", "views/", "wizard/", "wizards/", "data/", "report/", "reports/",
              "security/", "controllers/", "static/src/")
FUNCTIONAL_FILES = ("__manifest__.py", "readme/DESCRIPTION.md", "readme/USAGE.md", "readme/CONFIGURE.md")
FISA = "readme/FISA_CONSULTANT.md"
SHOTS = ("static/description/", "readme/screenshots/")
SHOT_TEST = "tests/test_screenshots.py"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def is_functional(rel: str) -> bool:
    return rel in FUNCTIONAL_FILES or rel.startswith(FUNCTIONAL)


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
        if mine and args.bot in author:
            last_fisa_by_bot[module] = order
        elif is_functional(rel) and args.bot not in author:
            last_change[module] = order

    selected = []
    for module, changed_at in sorted(last_change.items(), key=lambda kv: -kv[1]):
        if last_fisa_by_bot.get(module, 0) > changed_at:
            continue  # fișa (sau capturile) e deja la zi cu ultima schimbare
        if args.screenshots:
            if Path(module, SHOT_TEST).is_file():
                selected.append({"module": module, "action": "screenshots", "reason": "cod schimbat în PR"})
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
