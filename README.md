# ci-agents

The CI agents shared by the Odoo suites of terrabit-solutions, in one place, so a fix is
made once and reaches every suite.

| Agent | What it does | Workflow |
|---|---|---|
| Argus | Advisory AI review of every PR, drafts included; never blocks the merge | `.github/workflows/argus.yml` |
| Mentor | Writes or updates the consultant sheet of the modules a PR changes, has it audited, regenerates their screenshots; all as commits on the PR | `.github/workflows/mentor.yml` |

Both are reusable workflows (`workflow_call`), run on the self-hosted runners of the
organization. A suite outside the organization (`dhongu/deltatech`) passes
`runs-on: '"ubuntu-latest"'` and runs them on its own GitHub-hosted minutes.

## In a suite

```
.github/workflows/argus.yml      calls ci-agents/.github/workflows/argus.yml@main
.github/workflows/mentor.yml     calls ci-agents/.github/workflows/mentor.yml@main
.github/argus/REVIEW.local.md    optional: the suite's own review rules, read after argus/REVIEW.md
.github/mentor/private_repos.sh  the private clones of its test.yml (the only code with credentials)
.github/mentor/install.sh        what its test.yml installs before `pip install -r`
```

The suite's scripts and REVIEW.local.md are read from the PR's base branch, the rest from
this repository: a PR cannot change how it is reviewed or what Mentor commits.

## Here

- `argus/`: `REVIEW.md` (the rules), `comment.sh` and `needs-pacioli.sh` (the only writes
  Argus may make)
- `mentor/`: `MENTOR.md` (the rules), `select_modules.py`, `push_commit.py`,
  `push_screenshots.py`

## Requirements

- This repository is public, so any suite can call its workflows and check it out
  without a token. It holds no secrets: they stay with the suites.
- Apps installed on the suite's owner (the organization, or the user account for a suite
  outside it): Argus Terrabit (read, PR comments) and Mentor Terrabit (contents write).
  Argus Terrabit must also stay installed on terrabit-solutions: its token reads
  `l10n_ro_ent` (l10n_ro_doc_screenshots) and `terrabit-claude` for every suite.
- Secrets visible to the suite (org secrets, or repository secrets outside the org):
  `ARGUS_APP_*`, `MENTOR_APP_*`, `CLAUDE_CODE_OAUTH_TOKEN`, plus what its
  `private_repos.sh` uses (`BITSHOP`, `ENTERPRISE_TOKEN`, `TERRABIT_TOKEN`).
- Mentor's screenshot job uses `deltatech_doc_screenshots` from `dhongu/deltatech` (from
  the checkout, in deltatech itself).
