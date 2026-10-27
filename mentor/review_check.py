#!/usr/bin/env python3
"""Verificările fără AI ale lui Mentor în modul review: fișa există și e completă ca formă.

Mentor review nu scrie nimic pe PR: pentru fiecare modul schimbat funcțional verifică doar că
are fișa consultant și că ea respectă structura din `fisa-modul`. Partea aceasta e deterministă:

- fișa `readme/FISA_CONSULTANT.md` lipsește: critic (restul nu se mai verifică);
- lipsesc secțiuni numerotate 1–11 sau secțiunea 6 n-are niciun `### Pasul`: major;
- un pas din secțiunea 6 fără imagine `![]()`, un placeholder `[SCREENSHOT:` rămas sau o captură
  la care fișa trimite și care nu e în modul: major;
- o captură `NN_*.png` din modul la care fișa nu trimite: minor.

Dacă pașii acoperă tot ce schimbă PR-ul judecă recenzentul (Claude), după aceste verificări.

Folosire (din rădăcina repo-ului suitei):
    python3 review_check.py check <base_sha> <head_sha> <module.json>  > precheck.json
    python3 review_check.py merge <precheck.json> <recenzie.json>      > verificare.json
`check` scrie [{"module", "sheet", "sheet_changed", "findings"}]; `merge` adaugă constatările
recenzentului și scrie formatul `.mentor-verify.json`: [{"module", "verdict", "findings"}].
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

FISA = "readme/FISA_CONSULTANT.md"
SHOTS = ("static/description/", "readme/screenshots/")
SECTIONS = range(1, 12)
SECTION = re.compile(r"^##\s+(\d+)\.", re.M)
STEP = re.compile(r"^###\s+Pasul\b.*$", re.M)
SHOT_REF = re.compile(r"\(([^()\s]+\.png)\)")
# The screenshots of the flow (01_..., 02_...), not the icon, the banner or USAGE's images.
FLOW_SHOT = re.compile(r"^\d{2}_.+\.png$")


def finding(severity: str, text: str) -> dict:
    return {"severity": severity, "text": text}


def section(text: str, number: int) -> str:
    """The body of section `number`, up to the next numbered section."""
    matches = list(SECTION.finditer(text))
    for i, m in enumerate(matches):
        if int(m.group(1)) == number:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[m.end():end]
    return ""


def check_module(module: str, changed: set[str]) -> dict:
    path = Path(module, FISA)
    result = {"module": module, "sheet": path.is_file(), "sheet_changed": f"{module}/{FISA}" in changed,
              "findings": []}
    findings = result["findings"]
    if not result["sheet"]:
        findings.append(finding("critic", f"Lipsește fișa consultant `{FISA}`: PR-ul schimbă modulul "
                                          "funcțional, iar fișa nu există. Se face cu Mentor local (fisa-completa)."))
        return result
    text = path.read_text(encoding="utf-8")

    present = {int(n) for n in SECTION.findall(text)}
    missing = [str(n) for n in SECTIONS if n not in present]
    if missing:
        findings.append(finding("major", f"Lipsesc secțiunile {', '.join(missing)} din structura fișei (1–11)."))

    flow = section(text, 6)
    steps = list(STEP.finditer(flow))
    if 6 in present and not steps:
        findings.append(finding("major", "Secțiunea 6 (Flux de utilizare) n-are niciun pas `### Pasul N`."))
    no_image = []
    for i, m in enumerate(steps):
        end = steps[i + 1].start() if i + 1 < len(steps) else len(flow)
        body = flow[m.end():end]
        # A step that ends in an XML excerpt instead of a screenshot is fine (fisa-modul).
        if "![" not in body and "```xml" not in body:
            no_image.append(m.group(0).lstrip("#").strip())
    if no_image:
        findings.append(finding("major", "Pași fără captură: " + "; ".join(no_image) + "."))

    if "[SCREENSHOT:" in text:
        findings.append(finding("major", "Fișa are încă placeholdere `[SCREENSHOT: ...]`."))

    refs = {Path(r).name for r in SHOT_REF.findall(text)}
    shots = {p.name for d in SHOTS for p in Path(module, d).glob("*.png")}
    absent = sorted(refs - shots)
    if absent:
        findings.append(finding("major", "Capturi la care fișa trimite și care nu sunt în modul: "
                                + ", ".join(f"`{s}`" for s in absent) + "."))
    orphans = sorted(s for s in shots - refs if FLOW_SHOT.match(s))
    if orphans:
        findings.append(finding("minor", "Capturi din modul nefolosite în fișă: "
                                + ", ".join(f"`{s}`" for s in orphans) + "."))
    return result


def check(base: str, head: str, modules_path: str) -> list:
    modules = [m["module"] for m in json.load(open(modules_path, encoding="utf-8"))]
    changed = set(subprocess.run(["git", "diff", "--name-only", base, head], capture_output=True,
                                 text=True, check=True).stdout.split())
    return [check_module(m, changed) for m in modules]


def load(path: str) -> list:
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def merge(precheck_path: str, review_path: str) -> list:
    reviews = {r.get("module"): r for r in load(review_path) if isinstance(r, dict)}
    out = []
    for pre in load(precheck_path):
        module = pre["module"]
        review = reviews.get(module)
        findings = list(pre.get("findings") or [])
        if review:
            findings += review.get("findings") or []
            verdict = review.get("verdict") or "?"
        elif pre.get("sheet"):
            verdict = "NEVERIFICATĂ (recenzentul n-a raportat)"
            findings.append(finding("major", "Recenzentul n-a raportat: acoperirea pașilor n-a fost verificată."))
        else:
            verdict = "fișă lipsă"
        out.append({"module": module, "verdict": verdict, "findings": findings})
    return out


def main() -> None:
    if sys.argv[1:2] == ["check"] and len(sys.argv) == 5:
        data = check(*sys.argv[2:5])
    elif sys.argv[1:2] == ["merge"] and len(sys.argv) == 4:
        data = merge(*sys.argv[2:4])
    else:
        sys.exit(__doc__)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
