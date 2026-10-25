#!/usr/bin/env bash
# The only PR edit Argus may make: add the needs-pacioli label to the PR
# under review. No arguments, so the permission rule can match it exactly.
set -euo pipefail
gh pr edit "${PR_NUMBER:?PR_NUMBER is not set}" --add-label needs-pacioli
