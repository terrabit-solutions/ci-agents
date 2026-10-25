# ci-agents

The CI agents shared by the Odoo suites of terrabit-solutions, in one place, so a fix is
made once and reaches every suite.

| Agent | What it does | Workflow |
|---|---|---|
| Argus | Advisory AI review of every PR, drafts included; never blocks the merge | `.github/workflows/argus.yml` |
| Mentor | Writes or updates the consultant sheet of the modules a PR changes, has it audited, regenerates their screenshots; all as commits on the PR | `.github/workflows/mentor.yml` |

Both are reusable workflows (`workflow_call`), run on the self-hosted runners of the
organization.

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

- Actions access: this repository is "Accessible from repositories in the
  terrabit-solutions organization" (Settings, Actions, Access).
- Apps installed on the suite: Argus Terrabit (read, PR comments) and Mentor Terrabit
  (contents write). Org secrets visible to the suite: `ARGUS_APP_*`, `MENTOR_APP_*`,
  `CLAUDE_CODE_OAUTH_TOKEN`, plus what its `private_repos.sh` uses (`BITSHOP`,
  `ENTERPRISE_TOKEN`, `TERRABIT_TOKEN`).
- Mentor's screenshot job uses `deltatech_doc_screenshots` from `dhongu/deltatech`.
