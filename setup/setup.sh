#!/usr/bin/env bash
# Apply protect-main and invite the agent. Idempotent.
# Uses the caller's gh auth (the owner account). Never the agent's token.
# Usage: setup.sh OWNER/REPO AGENT_LOGIN
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=setup/common.sh
source "$SCRIPT_DIR/common.sh"

if [[ $# -ne 2 ]]; then
  usage "setup.sh"
fi
require_args "setup.sh" "$1" "$2"
init_log "setup"
trap 'on_unexpected $LINENO' ERR

step_auth() {
  local admin login_lc agent_lc
  if ! command -v gh >/dev/null 2>&1; then
    log_step FAIL "Check gh auth and admin" "gh is not on PATH"
    return 1
  fi
  if ! command -v jq >/dev/null 2>&1; then
    log_step FAIL "Check gh auth and admin" "jq is not on PATH"
    return 1
  fi
  if ! gh_api user; then
    log_step FAIL "Check gh auth and admin" "gh is not authenticated ($(collapse "$GH_API_ERROR")). Run gh auth login as the owner account."
    return 1
  fi
  LOGIN=$(jq -r '.login // empty' <<<"$GH_API_BODY")
  if [[ -z $LOGIN ]]; then
    log_step FAIL "Check gh auth and admin" "gh user response had no login"
    return 1
  fi
  login_lc=$(printf '%s' "$LOGIN" | tr '[:upper:]' '[:lower:]')
  agent_lc=$(printf '%s' "$AGENT" | tr '[:upper:]' '[:lower:]')
  if [[ $login_lc == "$agent_lc" ]]; then
    log_step FAIL "Check gh auth and admin" "authenticated as the agent account ${LOGIN}. Use the owner account. Never use the agent's token."
    return 1
  fi
  if ! gh_api "repos/${SLUG}"; then
    log_step FAIL "Check gh auth and admin" "cannot read ${SLUG} ($(collapse "$GH_API_ERROR"))"
    return 1
  fi
  admin=$(jq -r '.permissions.admin // false' <<<"$GH_API_BODY")
  DEFAULT_BRANCH=$(jq -r '.default_branch // empty' <<<"$GH_API_BODY")
  if [[ $admin != true ]]; then
    log_step FAIL "Check gh auth and admin" "authenticated as ${LOGIN} without admin on ${SLUG}"
    return 1
  fi
  if [[ -z $DEFAULT_BRANCH ]]; then
    log_step FAIL "Check gh auth and admin" "repository ${SLUG} has no default branch"
    return 1
  fi
  log_step OK "Check gh auth and admin" "authenticated as ${LOGIN} with admin on ${SLUG}"
  return 0
}

mark_empty_repo() {
  if gh_api "repos/${SLUG}/commits/${DEFAULT_BRANCH}"; then
    REPO_EMPTY=0
    return 0
  fi
  if is_empty_repo; then
    REPO_EMPTY=1
    return 0
  fi
  REPO_EMPTY=0
  return 1
}

step_ruleset() {
  local ids count id
  if ! mark_empty_repo; then
    log_step FAIL "Create or update ruleset protect-main" "cannot read ${DEFAULT_BRANCH} ($(collapse "$GH_API_ERROR"))"
    return 0
  fi
  if [[ $REPO_EMPTY -eq 1 ]]; then
    log_step FAIL "Create or update ruleset protect-main" "repository is empty; push an initial commit to ${DEFAULT_BRANCH}, then re-run"
    return 0
  fi
  if [[ ! -f $JSON_FILE ]]; then
    log_step FAIL "Create or update ruleset protect-main" "missing ${JSON_FILE}"
    return 0
  fi
  if ! jq -e . "$JSON_FILE" >/dev/null; then
    log_step FAIL "Create or update ruleset protect-main" "${JSON_FILE} is not valid JSON"
    return 0
  fi
  if ! gh_api --paginate --slurp "repos/${SLUG}/rulesets?includes_parents=false&per_page=100"; then
    log_step FAIL "Create or update ruleset protect-main" "cannot list rulesets ($(collapse "$GH_API_ERROR"))"
    return 0
  fi
  ids=$(jq -c "$LIST_RULESET_IDS_JQ" <<<"$GH_API_BODY")
  count=$(jq -r 'length' <<<"$ids")
  if [[ $count -gt 1 ]]; then
    log_step FAIL "Create or update ruleset protect-main" "found ${count} repository rulesets named protect-main; keep one and re-run"
    return 0
  fi
  if [[ $count -eq 0 ]]; then
    if ! gh_api --method POST "repos/${SLUG}/rulesets" --input "$JSON_FILE"; then
      log_step FAIL "Create or update ruleset protect-main" "create failed ($(collapse "$GH_API_ERROR"))"
      return 0
    fi
    log_step OK "Create or update ruleset protect-main" "created protect-main"
    return 0
  fi
  id=$(jq -r '.[0]' <<<"$ids")
  if ! gh_api "repos/${SLUG}/rulesets/${id}"; then
    log_step FAIL "Create or update ruleset protect-main" "cannot read ruleset ${id} ($(collapse "$GH_API_ERROR"))"
    return 0
  fi
  capture_ruleset_diff "$JSON_FILE" "$GH_API_BODY"
  if [[ $DIFF_RC -eq 0 ]]; then
    log_step SKIPPED "Create or update ruleset protect-main" "already matches setup/rulesets/protect-main.json"
    return 0
  fi
  if [[ $DIFF_RC -ne 1 ]]; then
    log_step FAIL "Create or update ruleset protect-main" "$DIFF_TEXT"
    return 0
  fi
  if ! gh_api --method PUT "repos/${SLUG}/rulesets/${id}" --input "$JSON_FILE"; then
    log_step FAIL "Create or update ruleset protect-main" "update failed ($(collapse "$GH_API_ERROR"))"
    return 0
  fi
  log_step OK "Create or update ruleset protect-main" "updated protect-main"
  return 0
}

step_invite() {
  local perm role pending
  if gh_api "repos/${SLUG}/collaborators/${AGENT}"; then
    if ! gh_api "repos/${SLUG}/collaborators/${AGENT}/permission"; then
      log_step FAIL "Invite ${AGENT} with write" "cannot read permission ($(collapse "$GH_API_ERROR"))"
      return 0
    fi
    perm=$(jq -r '.permission // empty' <<<"$GH_API_BODY")
    role=$(jq -r '.role_name // empty' <<<"$GH_API_BODY")
    if [[ $perm == admin || $role == admin ]]; then
      log_step OK "Invite ${AGENT} with write" "warning: ${AGENT} has admin. Expected write only. Left unchanged."
      return 0
    fi
    if [[ $perm == write ]]; then
      log_step SKIPPED "Invite ${AGENT} with write" "already a collaborator with write"
      return 0
    fi
    if ! gh_api --method PUT "repos/${SLUG}/collaborators/${AGENT}" -f permission=push; then
      log_step FAIL "Invite ${AGENT} with write" "cannot change role from ${perm:-unknown} ($(collapse "$GH_API_ERROR"))"
      return 0
    fi
    log_step OK "Invite ${AGENT} with write" "changed role from ${perm:-unknown} to write"
    return 0
  fi
  if ! is_not_found; then
    log_step FAIL "Invite ${AGENT} with write" "cannot check collaborator ($(collapse "$GH_API_ERROR"))"
    return 0
  fi
  if ! gh_api --paginate --slurp "repos/${SLUG}/invitations"; then
    log_step FAIL "Invite ${AGENT} with write" "cannot list invitations ($(collapse "$GH_API_ERROR"))"
    return 0
  fi
  pending=$(jq -r --arg login "$AGENT" "$PENDING_INVITE_JQ" <<<"$GH_API_BODY")
  if [[ $pending != 0 ]]; then
    log_step SKIPPED "Invite ${AGENT} with write" "invitation already pending; ${AGENT} must accept it"
    return 0
  fi
  if ! gh_api --method PUT "repos/${SLUG}/collaborators/${AGENT}" -f permission=push; then
    log_step FAIL "Invite ${AGENT} with write" "invite failed ($(collapse "$GH_API_ERROR"))"
    return 0
  fi
  log_step OK "Invite ${AGENT} with write" "invitation sent with write; ${AGENT} must accept it"
  return 0
}

step_codeowners() {
  if [[ $REPO_EMPTY -eq 1 ]]; then
    log_step FAIL "Check .github/CODEOWNERS on the default branch" "repository is empty; push an initial commit to ${DEFAULT_BRANCH}, then re-run"
    return 0
  fi
  if gh_api --method GET "repos/${SLUG}/contents/.github/CODEOWNERS" -f "ref=${DEFAULT_BRANCH}"; then
    log_step OK "Check .github/CODEOWNERS on the default branch" "present on ${DEFAULT_BRANCH}"
    return 0
  fi
  if is_not_found; then
    log_step OK "Check .github/CODEOWNERS on the default branch" "warning: missing on ${DEFAULT_BRANCH}. $(codeowners_hint)"
    return 0
  fi
  log_step FAIL "Check .github/CODEOWNERS on the default branch" "cannot read file ($(collapse "$GH_API_ERROR"))"
  return 0
}

if ! step_auth; then
  skip_remaining "not run: caller is not an authenticated admin" \
    "Create or update ruleset protect-main" \
    "Invite ${AGENT} with write" \
    "Check .github/CODEOWNERS on the default branch"
  finish
fi

step_ruleset
step_invite
step_codeowners
finish
