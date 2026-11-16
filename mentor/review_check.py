#!/usr/bin/env python3
"""Verificările fără AI ale lui Mentor în modul review: fișa există și e completă ca formă.

Mentor review nu scrie nimic pe PR: pentru fiecare modul schimbat funcțional verifică doar că
are fișa consultant și că ea respectă structura din `fisa-modul`. Partea aceasta e deterministă:

- fișa `readme/FISA_CONSULTANT.md` lipsește: critic (restul nu se mai verifică);
- lipsesc secțiuni numerotate 1–11 sau secțiunea 6 n-are niciun pas (`### Pasul`, iar la un modul
  pentru altă țară `### Step`): major;
- un pas din secțiunea 6 fără imagine `![]()`, un placeholder `[SCREENSHOT:` rămas sau o captură
  la care fișa trimite și care nu e în modul: major;
- o captură `NN_*.png` din modul la care fișa nu trimite: minor.

Cheia `consultant_sheet` din manifest schimbă ce se cere: `"simple"` e o fișă fără capturi (nu se
cer imagini la pași și nu se raportează capturile nefolosite), `"none"` înseamnă că modulul nu are
nevoie de fișă (nicio constatare). Fără cheie, fișa e `"full"`.

Limba fișei urmează țara modulului, din cheia `countries` a manifestului: un modul cu `countries`
fără `ro` (de ex. `["sk"]`) are fișa în engleză, cu pașii `### Step N` și capturile în
`static/description/en/` (interfața engleză, aceleași ca la `readme/USAGE.md`); un modul fără
`countries` sau cu `ro` între ele are fișa în română, cu `### Pasul N` și capturile în
`static/description/` sau `readme/screenshots/`. Un modul pentru altă țară acceptă și forma veche
(fișă în română), pentru fișele făcute înainte de regulă. Titlurile secțiunilor 1–11 se numără la fel în
ambele limbi.

Dacă pașii acoperă tot ce schimbă PR-ul judecă recenzentul (Claude), după aceste verificări.

Folosire (din rădăcina repo-ului suitei):
    python3 review_check.py check <base_sha> <head_sha> <module.json>  > precheck.json
    python3 review_check.py merge <precheck.json> <recenzie.json>      > verificare.json
`check` scrie [{"module", "sheet", "sheet_changed", "findings"}]; `merge` adaugă constatările
recenzentului și scrie formatul `.mentor-verify.json`: [{"module", "verdict", "findings"}].
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

FISA = "readme/FISA_CONSULTANT.md"
# Per language of the sheet: the headings of a step and where its screenshots are. The English
# sheets (modules for other countries) have the screenshots in en/, only in English. A module for
# another country keeps accepting the Romanian layout (`### Pasul`, screenshots in
# static/description/), because the sheets made before this rule are in Romanian.
LANGUAGES = {
    "ro": {"steps": ("Pasul",), "shots": ("static/description/", "readme/screenshots/")},
    "en": {"steps": ("Step", "Pasul"), "shots": ("static/description/en/", "static/description/",
                                                   "readme/screenshots/")},
}
SECTIONS = range(1, 12)
SECTION = re.compile(r"^##\s+(\d+)\.", re.M)
SHOT_REF = re.compile(r"\(([^()\s]+\.png)\)")
# The screenshots of the flow (01_..., 02_...), not the icon, the banner or USAGE's images.
FLOW_SHOT = re.compile(r"^\d{2}_.+\.png$")
SHEET_MODES = ("full", "simple", "none")


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


def manifest_of(module: str) -> dict:
    try:
        manifest = ast.literal_eval(Path(module, "__manifest__.py").read_text(encoding="utf-8"))
    except (OSError, ValueError, SyntaxError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def sheet_mode(module: str) -> str:
    """`consultant_sheet` from the module manifest: full (default), simple or none."""
    mode = manifest_of(module).get("consultant_sheet")
    return mode if mode in SHEET_MODES else "full"


def sheet_language(module: str) -> str:
    """`en` for a module made for other countries (`countries` without `ro`), else `ro`."""
    countries = manifest_of(module).get("countries")
    if isinstance(countries, (list, tuple)) and countries and "ro" not in {str(c).lower() for c in countries}:
        return "en"
    return "ro"


def check_module(module: str, changed: set[str]) -> dict:
    path = Path(module, FISA)
    mode = sheet_mode(module)
    lang = sheet_language(module)
    rules = LANGUAGES[lang]
    result = {"module": module, "sheet": path.is_file(), "sheet_changed": f"{module}/{FISA}" in changed,
              "consultant_sheet": mode, "sheet_language": lang, "findings": []}
    findings = result["findings"]
    if mode == "none":
        return result
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
    steps = list(re.finditer(rf"^###\s+(?:{'|'.join(rules['steps'])})\b.*$", flow, re.M))
    if 6 in present and not steps:
        findings.append(finding("major", f"Secțiunea 6 (Flux de utilizare) n-are niciun pas `### {rules['steps'][0]} N`"
                                         + (" (fișa unui modul pentru altă țară e în engleză)." if lang == "en" else ".")))
    no_image = []
    for i, m in enumerate(steps if mode == "full" else []):
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
    shots_by_dir = {d: {p.name for p in Path(module, d).glob("*.png")} for d in rules["shots"]}
    shots = set().union(*shots_by_dir.values())
    absent = sorted(refs - shots)
    if absent:
        findings.append(finding("major", "Capturi la care fișa trimite și care nu sunt în modul: "
                                + ", ".join(f"`{s}`" for s in absent) + "."))
    scanned = shots
    if lang == "en":
        # only the folders the sheet refers to: the other ones (the English set of a Romanian
        # sheet, which USAGE.md uses) are not its screenshots
        used = [d for d, names in shots_by_dir.items() if names & refs] or [rules["shots"][0]]
        scanned = set().union(*(shots_by_dir[d] for d in used))
    orphans = sorted(s for s in scanned - refs if FLOW_SHOT.match(s))
    if orphans and mode == "full":
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
        elif pre.get("consultant_sheet") == "none":
            verdict = "fără fișă (consultant_sheet: none)"
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
