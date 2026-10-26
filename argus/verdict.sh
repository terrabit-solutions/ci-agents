#!/usr/bin/env bash
# The review's counts, for the step that may move a clean draft to Ready: blocking,
# important and minor issues, as three whole numbers. That step checks them against the
# inline comments Argus posted, so they only ever hold a draft back.
set -euo pipefail
[ $# -eq 3 ] || { echo "usage: .argus/verdict.sh <blocking> <important> <minor>" >&2; exit 2; }
for n in "$@"; do
  [[ "$n" =~ ^[0-9]+$ ]] || { echo "not a whole number: $n" >&2; exit 2; }
done
printf '%s %s %s\n' "$1" "$2" "$3" > "${RUNNER_TEMP:?RUNNER_TEMP is not set}/argus-verdict"
echo "verdict: $1 blocking, $2 important, $3 minor"
