#!/usr/bin/env bash
# The only way Pacioli's pre-check may post: one PR comment, its text as one argument. It must
# open with "## Pre-verificare Pacioli", never "## Verificare Pacioli" (the human verdict that
# opens Argus's needs-pacioli gate), and has no "Verdict:" line; the reviewed commit is appended.
set -euo pipefail
[ $# -eq 1 ] || { echo 'usage: .pacioli/comment.sh "<comment>"' >&2; exit 2; }
case "$1" in
  "## Pre-verificare Pacioli"*) ;;
  *) echo 'The comment must start with "## Pre-verificare Pacioli".' >&2; exit 2 ;;
esac
if grep -qiE '^[[:space:]]*(verdict|commit):' <<< "$1"; then
  echo 'No "Verdict:" or "Commit:" line: write "**Verdict propus: ...**", the script adds the commit.' >&2
  exit 2
fi
gh pr comment "${PR_NUMBER:?PR_NUMBER is not set}" \
  --body "$1"$'\n\n'"Commit: ${HEAD_SHA:?HEAD_SHA is not set}"
touch "${RUNNER_TEMP:?RUNNER_TEMP is not set}/pacioli-posted"
