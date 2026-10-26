# ci-agents

The CI agents shared by the Odoo suites of terrabit-solutions, in one place, so a fix is
made once and reaches every suite.

| Agent | What it does | Workflow |
|---|---|---|
| Argus | Advisory AI review of every PR, drafts included; never blocks the merge. A draft with no blocking or important issue goes to Ready by itself (label `wip` keeps it a draft) | `.github/workflows/argus.yml` |
| Mentor | As the fisa-completa skill, in three jobs: writes or updates the consultant sheet of the modules a PR changes functionally, regenerates the screenshots whose screens changed or that the sheet calls for (view, wizard or OWL XML, the screenshot test, new steps in the sheet), then has the sheet audited against them, up to three rounds of fixes; all as commits on the PR, with the report as one PR comment | `.github/workflows/mentor.yml` |
| Automerge | Merges a PR labelled `automerge` once Argus is clean (`argus-ok`), Mentor is done and clean (`mentor-ok`), nothing runs on its branch and every run on its head passed; `wip`, `needs-pacioli` and `no-merge` stop it. No AI | `.github/workflows/automerge.yml` |

Both are reusable workflows (`workflow_call`), run on the self-hosted runners of the
organization: the light jobs (Argus, Mentor's sheet, the screenshots commit) on the ones
labelled `agents`, kept for the agents, and Mentor's screenshots (Odoo + Chrome) on the
`odoo` ones, with the tests. A suite outside the organization (`dhongu/deltatech`) passes
`runs-on: '"ubuntu-latest"'` and runs them on its own GitHub-hosted minutes.
It also passes the secrets by name (`secrets: inherit` only works inside the organization).

Argus takes `lint: true` (off by default, pilot on bitshop): it first runs `tb-odoo-lint`
from `dhongu/terrabit-pre-commit-hooks` (fixed commit) on the PR's `.py`/`.xml` files and
hands the findings to Argus as `.argus/lint.json`, to confirm or reject on the PR's lines.

Argus and Mentor take `odoo-version` (default `"19.0"`), the series of the branch the
caller lives on: the Odoo core Argus checks the API against (and the version it gives to the
rules, which have a section per series), the OCA image of Mentor's screenshots job
(`py3.10-odoo19.0`, `py3.12-odoo20.0`) and the branch the screenshot tooling and the RO
accounting reference come from. Each branch of a suite has its own callers (`branches:` and
`odoo-version:` set to that series).

Automerge needs no version, but GitHub fires `workflow_run` only from the workflow file on
the default branch: the 19.0 caller looks after the PRs to every branch once their workflows
end. A 20.0 caller only adds the `pull_request: labeled` trigger, which reads the workflow file
of the PR's base branch.

## In a suite

```
.github/workflows/argus.yml      calls ci-agents/.github/workflows/argus.yml@main
.github/workflows/mentor.yml     calls ci-agents/.github/workflows/mentor.yml@main
.github/workflows/automerge.yml  calls ci-agents/.github/workflows/automerge.yml@main, after each PR workflow
.github/argus/REVIEW.local.md    optional: the suite's own review rules, read after the shared rules
.github/mentor/private_repos.sh  the private clones of its test.yml (the only code with credentials)
.github/mentor/install.sh        what its test.yml installs before `pip install -r`
```

The suite's scripts and REVIEW.local.md are read from the PR's base branch, the shared rules
from `terrabit-claude` main and the rest from this repository: a PR cannot change how it is
reviewed or what Mentor commits.

## Here

- `argus/`: `comment.sh` and `needs-pacioli.sh` (the only writes Argus may make),
  `verdict.sh` (the counts; a workflow step, not Argus, moves the draft)
- `mentor/`: `select_modules.py`, `push_commit.py`, `push_screenshots.py`, `pr_comment.py`,
  `show_sessions.py`, `carry_result.py`

The rules themselves (Argus's `REVIEW.md`, Mentor's `MENTOR.md`) are not here: they live in
`ci-agents/` of the private `terrabit-solutions/terrabit-claude` and are read with the Argus
Terrabit token, so only the plumbing is public.

## Requirements

- This repository is public, so any suite can call its workflows and check it out
  without a token, including the public `dhongu/deltatech` (a public repository cannot call
  a private one's workflows). It holds no secrets and no rules: they stay with the suites
  and in `terrabit-claude`.
- Apps installed on the suite's owner (the organization, or the user account for a suite
  outside it): Argus Terrabit (contents write, PR comments; Claude gets a read-only token, the write one only marks a clean draft ready) and Mentor Terrabit (contents write).
  Argus Terrabit must also stay installed on terrabit-solutions: its token reads
  `l10n_ro_ent` (l10n_ro_doc_screenshots) and `terrabit-claude` (the rules, the fisa-modul skill) for
  every suite.
- Secrets visible to the suite (org secrets, or repository secrets outside the org):
  `ARGUS_APP_*`, `MENTOR_APP_*`, `CLAUDE_CODE_OAUTH_TOKEN`, plus what its
  `private_repos.sh` uses (`BITSHOP`, `ENTERPRISE_TOKEN`, `TERRABIT_TOKEN`).
- Mentor's screenshot job uses `deltatech_doc_screenshots` from `dhongu/deltatech` (from
  the checkout, in deltatech itself) when the series has it (not 20.0 yet).
