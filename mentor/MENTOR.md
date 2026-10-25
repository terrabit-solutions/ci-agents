# Mentor — fișa consultant în PR

Mentor lucrează pe un PR care schimbă funcțional unul sau mai multe module (lista e în
`.mentor-modules.json`) și ține la zi fișa consultant `<modul>/readme/FISA_CONSULTANT.md`, ca ea să
descrie codul din acest PR. Workflow-ul pornește trei roluri, fiecare într-o sesiune separată:
**autorul** scrie fișa, **verificatorul** o auditează, iar dacă rămân probleme 🔴/🟠, **autorul** le
corectează și verificatorul se uită din nou. Promptul îți spune ce rol ai.

## Unde sunt lucrurile

- Repo-ul suitei e în rădăcină: modulul e `<modul>/`, cu `__manifest__.py`.
- `.mentor/fisa-modul/SKILL.md`: structura fișei și regulile ei.
- `.mentor/verificator-fisa.md`: instrucțiunile verificatorului.
- `.mentor/pr.diff`: diff-ul PR-ului pe modulele din listă.
- Referința contabilă RO: `odoo-addons/l10n_ro_ent/skills/contabilitate-ro/`; fișa model pomenită de
  `fisa-modul`: `odoo-addons/l10n_ro_ent/`.

## Autorul

Pentru fiecare modul, în ordine:

1. **`action: "update"`** — citește fișa existentă și diff-ul PR-ului pe modul, din
   `.mentor/pr.diff`. Schimbă doar ce s-a schimbat în cod: un câmp, un pas, un
   meniu, o notă contabilă. Nu rescrie fișa de la zero și nu-i schimba stilul.
   **`action: "create"`** — scrie fișa nouă după `.mentor/fisa-modul/SKILL.md`.
2. **Capturile** nu le poți face aici. Păstrează referințele la cele existente; pentru un ecran nou
   sau schimbat, folosește convenția de nume din `fisa-modul` și trece numele în raport. Nu lăsa
   `[SCREENSHOT: ...]` în fișă.
3. Scrie `.mentor-report.json`: o listă cu câte un obiect pe modul,
   `{"module", "action", "screenshots": [...]}`.

**La corectare** (promptul îți spune asta), citește constatările din `.mentor-verify.json` și
corectează țintit 🔴 și 🟠 (și 🟡 ușor de rezolvat). Nu rescrie fișa.

## Verificatorul

Pentru fiecare modul, auditează fișa după `.mentor/verificator-fisa.md`, pe codul din acest PR.
Nu modifici fișa. Scrie `.mentor-verify.json`: o listă cu câte un obiect pe modul,
`{"module", "verdict", "findings": [{"severity": "critic|major|minor|observație", "text"}]}`.
`verdict` e verdictul tău, pe scurt; `text` e constatarea, într-o frază.

## Reguli pentru toate rolurile

- Autorul scrie doar în `<modul>/readme/FISA_CONSULTANT.md` și în `.mentor-report.json`;
  verificatorul doar în `.mentor-verify.json`.
- Citești fișiere cu Read, Grep și Glob; diff-ul PR-ului e în `.mentor/pr.diff`. Din shell ai doar
  `ls`, câte o comandă simplă, fără `cd`, `&&`, `;` sau pipe-uri. Nu porni subagenți: lucrezi tu, până la capăt.
- Nu inventa bază legală, conturi, meniuri sau câmpuri: tot ce scrii se verifică în codul
  modulului sau în referința contabilă. Ce nu poți verifica, lași deoparte.
- Română corectă, cu diacritice. Fără SAGA în fișă.
- Nu atinge `readme/HISTORY.md`, versiunea, codul sau testele.
- Termini abia după ce ai scris fișierul JSON al rolului tău.
