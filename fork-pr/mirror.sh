#!/usr/bin/env bash
# Mirrors a fork's pull request into the branch fork-pr/<number> of the suite and opens a PR
# from it, so the suite's CI (ci-gate, tests, Argus, Mentor) runs on the fork's commit. Run by a
# maintainer, with their own gh login, only after reading the diff: the CI runs that code on the
# org's runners with the org's secrets. A PR opened with the workflow token would start no
# workflow, hence a script and not a workflow.
#
#   fork-pr/mirror.sh <owner/repo> <pr-number>
#
# Again after each push on the fork: it moves the branch to the new head. Once the fork's PR is
# merged (or the mirror, with a merge commit, which marks the fork's PR merged too), close the
# other one and delete the branch.
set -euo pipefail

repo=${1:?owner/repo}
pr=${2:?pr number}
branch="fork-pr/$pr"

IFS=$'\t' read -r sha base cross title < <(
    gh pr view "$pr" -R "$repo" --json headRefOid,baseRefName,isCrossRepository,title \
        --jq '[.headRefOid, .baseRefName, (.isCrossRepository | tostring), .title] | @tsv'
)
if [ "$cross" != "true" ]; then
    echo "#$pr is not from a fork: its CI already runs."
    exit 1
fi

# Workflow files changed by a fork would run with the org's secrets on the mirror.
workflows=$(gh pr diff "$pr" -R "$repo" --name-only | grep '^\.github/' || true)
if [ -n "$workflows" ] && [ "${ALLOW_GITHUB_CHANGES:-}" != "1" ]; then
    echo "#$pr changes .github/ (ALLOW_GITHUB_CHANGES=1 to mirror it anyway):"
    echo "$workflows"
    exit 1
fi

# The fork's commits are already in the suite (refs/pull/<n>/head), so the branch is a ref.
if gh api "repos/$repo/git/ref/heads/$branch" >/dev/null 2>&1; then
    gh api -X PATCH "repos/$repo/git/refs/heads/$branch" -f sha="$sha" -F force=true >/dev/null
    echo "$branch moved to $sha"
else
    gh api "repos/$repo/git/refs" -f ref="refs/heads/$branch" -f sha="$sha" >/dev/null
    echo "$branch created at $sha"
fi

mirror=$(gh pr list -R "$repo" --head "$branch" --state open --json url --jq '.[0].url // ""')
if [ -z "$mirror" ]; then
    # Not a draft: the suites' tests wait for Ready.
    mirror=$(gh pr create -R "$repo" --base "$base" --head "$branch" --title "$title" \
        --body "CI mirror of #$pr (from a fork), made by fork-pr/mirror.sh after reading the diff. Merge #$pr, or this one with a merge commit; then close the other and delete \`$branch\`.")
fi
echo "Mirror: $mirror"
