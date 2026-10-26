# Sourced by the steps of the screenshots job that clone: the VPS runners lose DNS now and
# then ("Could not resolve host: github.com"), which used to fail the job at the first clone.
# A git command that ends with exit 128 (git's fatal error: network, auth) is retried twice;
# any other exit code is git's answer (ls-remote --exit-code gives 2 for a missing branch)
# and is returned at once. The last failure still fails the step.
git() {
  local try rc
  for try in 1 2 3; do
    command git "$@" && return 0
    rc=$?
    if [ "$rc" != 128 ] || [ "$try" = 3 ]; then
      return "$rc"
    fi
    echo "::warning::git failed (exit 128), retrying in $((try * 15)) s ($try/2)" >&2
    sleep $((try * 15))
  done
}
