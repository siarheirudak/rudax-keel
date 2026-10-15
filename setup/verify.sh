#!/usr/bin/env bash
# Read-only check of protect-main, the agent role, and CODEOWNERS.
# Uses the caller's gh auth. Does not change the repository.
# Usage: verify.sh OWNER/REPO AGENT_LOGIN
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=setup/common.sh
source "$SCRIPT_DIR/common.sh"

if [[ $# -ne 2 ]]; then
  usage "verify.sh"
fi
require_args "verify.sh" "$1" "$2"
init_log "verify"
trap 'on_unexpected $LINENO' ERR

step_auth() {
  if ! command -v gh >/dev/null 2>&1; then
    log_step FAIL "Check gh auth" "gh is not on PATH"
    return 1
  fi
  if ! command -v jq >/dev/null 2>&1; then
    log_step FAIL "Check gh auth" "jq is not on PATH"
    return 1
  fi
  if ! gh_api user; then
    log_step FAIL "Check gh auth" "gh is not authenticated ($(collapse "$GH_API_ERROR")). Run gh auth login as the owner account."
    return 1
  fi
  LOGIN=$(jq -r '.login // empty' <<<"$GH_API_BODY")
  if [[ -z $LOGIN ]]; then
    log_step FAIL "Check gh auth" "gh user response had no login"
    return 1
  fi
  if ! gh_api "repos/${SLUG}"; then
    log_step FAIL "Check gh auth" "cannot read ${SLUG} ($(collapse "$GH_API_ERROR"))"
    return 1
  fi
  DEFAULT_BRANCH=$(jq -r '.default_branch // empty' <<<"$GH_API_BODY")
  if [[ -z $DEFAULT_BRANCH ]]; then
    log_step FAIL "Check gh auth" "repository ${SLUG} has no default branch"
    return 1
  fi
  log_step OK "Check gh auth" "authenticated as ${LOGIN}"
  return 0
}

step_ruleset() {
  local ids count id diff_text
  if ! gh_api "repos/${SLUG}/commits/${DEFAULT_BRANCH}"; then
    if is_empty_repo; then
      REPO_EMPTY=1
      log_step FAIL "Compare live ruleset with protect-main.json" "repository is empty; push an initial commit to ${DEFAULT_BRANCH}, then re-run"
      return 0
    fi
    log_step FAIL "Compare live ruleset with protect-main.json" "cannot read ${DEFAULT_BRANCH} ($(collapse "$GH_API_ERROR"))"
    return 0
  fi
  if [[ ! -f $JSON_FILE ]]; then
    log_step FAIL "Compare live ruleset with protect-main.json" "missing ${JSON_FILE}"
    return 0
  fi
  if ! gh_api --paginate --slurp "repos/${SLUG}/rulesets?includes_parents=false&per_page=100"; then
    log_step FAIL "Compare live ruleset with protect-main.json" "cannot list rulesets ($(collapse "$GH_API_ERROR")). Reading rulesets requires admin on the repo."
    return 0
  fi
  ids=$(jq -c "$LIST_RULESET_IDS_JQ" <<<"$GH_API_BODY")
  count=$(jq -r 'length' <<<"$ids")
  if [[ $count -eq 0 ]]; then
    log_step FAIL "Compare live ruleset with protect-main.json" "no repository ruleset named protect-main"
    return 0
  fi
  if [[ $count -gt 1 ]]; then
    log_step FAIL "Compare live ruleset with protect-main.json" "found ${count} repository rulesets named protect-main"
    return 0
  fi
  id=$(jq -r '.[0]' <<<"$ids")
  if ! gh_api "repos/${SLUG}/rulesets/${id}"; then
    log_step FAIL "Compare live ruleset with protect-main.json" "cannot read ruleset ${id} ($(collapse "$GH_API_ERROR"))"
    return 0
  fi
  capture_ruleset_diff "$JSON_FILE" "$GH_API_BODY"
  if [[ $DIFF_RC -eq 0 ]]; then
    log_step OK "Compare live ruleset with protect-main.json" "protect-main matches"
    return 0
  fi
  diff_text=$DIFF_TEXT
  if [[ ${#diff_text} -gt 500 ]]; then
    diff_text="${diff_text:0:500}..."
  fi
  if [[ $DIFF_RC -ne 1 ]]; then
    log_step FAIL "Compare live ruleset with protect-main.json" "$diff_text"
    return 0
  fi
  log_step FAIL "Compare live ruleset with protect-main.json" "$diff_text"
  return 0
}

step_agent() {
  local perm role pending
  if ! gh_api "repos/${SLUG}/collaborators/${AGENT}"; then
    if ! is_not_found; then
      log_step FAIL "Check agent role is write" "cannot check collaborator ($(collapse "$GH_API_ERROR"))"
      return 0
    fi
    if ! gh_api --paginate --slurp "repos/${SLUG}/invitations"; then
      log_step FAIL "Check agent role is write" "not a collaborator, and invitations could not be read ($(collapse "$GH_API_ERROR"))"
      return 0
    fi
    pending=$(jq -r --arg login "$AGENT" "$PENDING_INVITE_JQ" <<<"$GH_API_BODY")
    if [[ $pending != 0 ]]; then
      log_step FAIL "Check agent role is write" "invitation pending; ${AGENT} must accept it"
      return 0
    fi
    log_step FAIL "Check agent role is write" "${AGENT} is not a collaborator with write"
    return 0
  fi
  if ! gh_api "repos/${SLUG}/collaborators/${AGENT}/permission"; then
    log_step FAIL "Check agent role is write" "cannot read permission ($(collapse "$GH_API_ERROR"))"
    return 0
  fi
  perm=$(jq -r '.permission // empty' <<<"$GH_API_BODY")
  role=$(jq -r '.role_name // empty' <<<"$GH_API_BODY")
  if [[ $perm == admin || $role == admin ]]; then
    log_step FAIL "Check agent role is write" "role is admin, expected write"
    return 0
  fi
  if [[ $perm == write ]]; then
    log_step OK "Check agent role is write" "${AGENT} has write"
    return 0
  fi
  log_step FAIL "Check agent role is write" "role is ${perm:-unknown}, expected write"
  return 0
}

step_codeowners() {
  if [[ $REPO_EMPTY -eq 1 ]]; then
    log_step FAIL "Check .github/CODEOWNERS on the default branch" "repository is empty; push an initial commit to ${DEFAULT_BRANCH}, then add the file"
    return 0
  fi
  if gh_api --method GET "repos/${SLUG}/contents/.github/CODEOWNERS" -f "ref=${DEFAULT_BRANCH}"; then
    log_step OK "Check .github/CODEOWNERS on the default branch" "present on ${DEFAULT_BRANCH}"
    return 0
  fi
  if is_not_found; then
    log_step FAIL "Check .github/CODEOWNERS on the default branch" "missing on ${DEFAULT_BRANCH}. $(codeowners_hint)"
    return 0
  fi
  log_step FAIL "Check .github/CODEOWNERS on the default branch" "cannot read file ($(collapse "$GH_API_ERROR"))"
  return 0
}

if ! step_auth; then
  skip_remaining "not run: gh auth check failed" \
    "Compare live ruleset with protect-main.json" \
    "Check agent role is write" \
    "Check .github/CODEOWNERS on the default branch"
  finish
fi

step_ruleset
step_agent
step_codeowners
finish
