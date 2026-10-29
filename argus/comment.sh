#!/usr/bin/env bash
# The only way Argus may post its summary: the text comes as one argument,
# so `gh pr comment --body-file` cannot be used to publish a runner file.
# Posted as a "comment" review, so Argus shows under Reviewers even without
# inline comments; the approval or the change request comes after it, from
# review_verdict.py, decided by the workflow from the counts, not by Claude.
set -euo pipefail
[ $# -eq 1 ] || { echo "usage: .argus/comment.sh \"<summary>\"" >&2; exit 2; }
gh pr review "${PR_NUMBER:?PR_NUMBER is not set}" --comment --body "$1"
