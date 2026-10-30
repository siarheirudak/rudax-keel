#!/usr/bin/env bash
# Read-only check of the GitHub rules. Does not change the repository.
# Usage: verify-github-rules.sh OWNER/REPO AGENT_LOGIN [--accept-risk] [--no-emoji]
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=setup/common.sh
source "$SCRIPT_DIR/common.sh"

positional=()
for arg in "$@"; do
  case $arg in
    --accept-risk) ACCEPT_RISK=1 ;;
    --no-emoji) NO_EMOJI_FLAG=1 ;;
    -*)
      printf 'Unknown option: %s\n' "$arg" >&2
      usage "verify-github-rules.sh"
      ;;
    *) positional+=("$arg") ;;
  esac
done
if [[ ${#positional[@]} -ne 2 ]]; then
  usage "verify-github-rules.sh"
fi
require_args "verify-github-rules.sh" "${positional[0]}" "${positional[1]}"
init_log "verify"
trap 'on_unexpected $LINENO' ERR

REST_WHAT=(
  "Compare live ruleset with protect-main.json"
  "Compare live ruleset with protect-tags.json"
  "Compare live ruleset with require-checks.json"
  "Check agent role is write"
  "Check CODEOWNERS matches the owner GitHub account"
  "Check GITHUB_TOKEN permissions are read-only"
  "Check fork pull request approval"
  "Check allowed actions"
  "Check actions are pinned to a commit SHA"
)
REST_ANCHOR=(
  protect-main
  protect-tags
  require-checks
  agent-write-access
  codeowners
  read-only-token
  fork-approval
  pinned-actions
  pinned-actions
)

skip_rest() {
  local reason=$1 i
  for ((i = 0; i < ${#REST_WHAT[@]}; i++)); do
    log_step FAIL "${REST_WHAT[$i]}" "$reason" "${REST_ANCHOR[$i]}"
  done
}

step_auth() {
  if ! prepare_auth; then
    log_step FAIL "Check gh auth" "$AUTH_ERROR" "who-runs-this"
    return 1
  fi
  log_step OK "Check gh auth" "authenticated as ${LOGIN} with admin on ${SLUG}" "who-runs-this"
  return 0
}

step_risk_reminder() {
  if [[ $RULESETS_OFF -eq 0 ]]; then
    return 0
  fi
  log_step FAIL "Free private ruleset risk" "$RISK_REASON" "free-private-risk"
  return 0
}

verify_named_ruleset() {
  local name=$1 anchor=$2
  local file="$SCRIPT_DIR/rulesets/${name}.json"
  local what="Compare live ruleset with ${name}.json"
  local ids count id enf

  if [[ $RULESETS_OFF -eq 1 ]]; then
    log_step FAIL "$what" "$RISK_REASON" "$anchor"
    return 0
  fi
  if ! mark_empty_repo; then
    log_step FAIL "$what" "cannot read ${DEFAULT_BRANCH} ($(collapse "$GH_API_ERROR"))" "$anchor"
    return 0
  fi
  if [[ $REPO_EMPTY -eq 1 ]]; then
    log_step FAIL "$what" "repository is empty; push an initial commit to ${DEFAULT_BRANCH}, then re-run" "$anchor"
    return 0
  fi
  if [[ $name == require-checks ]]; then
    require_checks_files_ready
    if [[ $REQUIRE_CHECKS_FILES -eq 2 ]]; then
      log_step FAIL "$what" "cannot read workflows on ${DEFAULT_BRANCH} ($(collapse "$GH_API_ERROR"))" "$anchor"
      return 0
    fi
    if [[ $REQUIRE_CHECKS_FILES -ne 1 ]]; then
      log_step "NOT YET" "$what" "$CHECKS_SKIP_REASON" "$anchor"
      return 0
    fi
  fi
  if [[ ! -f $file ]]; then
    log_step FAIL "$what" "missing ${file}" "$anchor"
    return 0
  fi
  if ! gh_api_collect "repos/${SLUG}/rulesets?includes_parents=false&per_page=100"; then
    log_step FAIL "$what" "cannot list rulesets ($(collapse "$GH_API_ERROR")). Reading rulesets requires admin on the repo." "$anchor"
    return 0
  fi
  ids=$(ruleset_ids "$name")
  count=$(jq -r 'length' <<<"$ids")
  if [[ $count -eq 0 ]]; then
    if [[ $name == require-checks ]]; then
      log_step FAIL "$what" "$OWNER_APPLY_REASON" "$anchor"
      warn_if_checks_red
    else
      log_step FAIL "$what" "no repository ruleset named ${name}" "$anchor"
    fi
    return 0
  fi
  if [[ $count -gt 1 ]]; then
    log_step FAIL "$what" "found ${count} repository rulesets named ${name}" "$anchor"
    return 0
  fi
  id=$(jq -r '.[0]' <<<"$ids")
  if ! gh_api "repos/${SLUG}/rulesets/${id}"; then
    log_step FAIL "$what" "cannot read ruleset ${id} ($(collapse "$GH_API_ERROR"))" "$anchor"
    return 0
  fi
  enf=$(jq -r '.enforcement // empty' <<<"$GH_API_BODY")
  if [[ $enf != active ]]; then
    if [[ $name == require-checks ]]; then
      log_step FAIL "$what" "$OWNER_APPLY_REASON" "$anchor"
      warn_if_checks_red
    else
      log_step FAIL "$what" "${name} enforcement is ${enf:-unknown}, expected active" "$anchor"
    fi
    return 0
  fi
  capture_ruleset_diff "$file" "$GH_API_BODY"
  if [[ $DIFF_RC -eq 0 ]]; then
    log_step ALREADY "$what" "${name} matches" "$anchor"
    if [[ $name == require-checks ]]; then
      warn_if_checks_red
    fi
    return 0
  fi
  if [[ $name == require-checks && $DIFF_RC -eq 1 ]]; then
    log_step FAIL "$what" "$OWNER_APPLY_REASON" "$anchor"
    warn_if_checks_red
    return 0
  fi
  log_step FAIL "$what" "$(shorten "$DIFF_TEXT")" "$anchor"
  return 0
}

step_agent() {
  local what="Check agent role is write" perm role pending
  if ! gh_api "repos/${SLUG}/collaborators/${AGENT}"; then
    if ! is_not_found; then
      log_step FAIL "$what" "cannot check collaborator ($(collapse "$GH_API_ERROR"))" "agent-write-access"
      return 0
    fi
    if ! gh_api_collect "repos/${SLUG}/invitations"; then
      log_step FAIL "$what" "not a collaborator, and invitations could not be read ($(collapse "$GH_API_ERROR"))" "agent-write-access"
      return 0
    fi
    pending=$(jq -r --arg login "$AGENT" "$PENDING_INVITE_JQ" <<<"$GH_API_BODY")
    if [[ $pending != 0 ]]; then
      log_step FAIL "$what" "invitation pending; the agent GitHub account must accept it" "agent-write-access"
      return 0
    fi
    log_step FAIL "$what" "${AGENT} is not a collaborator with write" "agent-write-access"
    return 0
  fi
  if ! gh_api "repos/${SLUG}/collaborators/${AGENT}/permission"; then
    log_step FAIL "$what" "cannot read permission ($(collapse "$GH_API_ERROR"))" "agent-write-access"
    return 0
  fi
  perm=$(jq -r '.permission // empty' <<<"$GH_API_BODY")
  role=$(jq -r '.role_name // empty' <<<"$GH_API_BODY")
  if [[ $perm == admin || $role == admin ]]; then
    log_step FAIL "$what" "role is admin, expected write" "agent-write-access"
    return 0
  fi
  if [[ $perm == write ]]; then
    log_step ALREADY "$what" "${AGENT} has write" "agent-write-access"
    return 0
  fi
  log_step FAIL "$what" "role is ${perm:-unknown}, expected write" "agent-write-access"
  return 0
}

step_codeowners() {
  local what="Check CODEOWNERS matches the owner GitHub account" st text
  if [[ $REPO_EMPTY -eq 1 ]]; then
    log_step FAIL "$what" "repository is empty; push an initial commit to ${DEFAULT_BRANCH}, then re-run" "codeowners"
    return 0
  fi
  st=0
  branch_file_status ".github/CODEOWNERS" || st=$?
  if [[ $st -eq 1 ]]; then
    log_step FAIL "$what" "missing on ${DEFAULT_BRANCH}. Expected \`* @${LOGIN}\`." "codeowners"
    return 0
  fi
  if [[ $st -ne 0 ]]; then
    log_step FAIL "$what" "cannot read file ($(collapse "$GH_API_ERROR"))" "codeowners"
    return 0
  fi
  decode_content_body
  text=$CONTENT_TEXT
  if codeowners_matches "$text"; then
    log_step ALREADY "$what" "matches * @${LOGIN}" "codeowners"
    return 0
  fi
  log_step FAIL "$what" "does not match * @${LOGIN}" "codeowners"
  return 0
}

step_token() {
  local what="Check GITHUB_TOKEN permissions are read-only" perms approve
  if ! gh_api "repos/${SLUG}/actions/permissions/workflow"; then
    log_step FAIL "$what" "cannot read workflow permissions ($(collapse "$GH_API_ERROR"))" "read-only-token"
    return 0
  fi
  perms=$(jq -r '.default_workflow_permissions // empty' <<<"$GH_API_BODY")
  approve=$(jq -r '.can_approve_pull_request_reviews // false' <<<"$GH_API_BODY")
  if [[ $perms == read && $approve == false ]]; then
    log_step ALREADY "$what" "read-only and cannot approve pull requests" "read-only-token"
    return 0
  fi
  log_step FAIL "$what" "default_workflow_permissions is ${perms:-unknown}, can_approve_pull_request_reviews is ${approve:-unknown}" "read-only-token"
  return 0
}

step_fork() {
  local what="Check fork pull request approval" policy
  if [[ $PRIVATE -eq 1 ]]; then
    log_step OK "$what" "not applicable (private repo)" "fork-approval"
    return 0
  fi
  if ! gh_api "repos/${SLUG}/actions/permissions/fork-pr-contributor-approval"; then
    if is_not_found; then
      log_step FAIL "$what" "$FORK_MANUAL_REASON" "fork-approval"
      return 0
    fi
    log_step FAIL "$what" "cannot read fork approval ($(collapse "$GH_API_ERROR"))" "fork-approval"
    return 0
  fi
  policy=$(jq -r '.approval_policy // empty' <<<"$GH_API_BODY")
  if [[ $policy == all_external_contributors ]]; then
    log_step ALREADY "$what" "requires approval for all outside collaborators" "fork-approval"
    return 0
  fi
  log_step FAIL "$what" "approval_policy is ${policy:-unknown}, expected all_external_contributors" "fork-approval"
  return 0
}

step_actions() {
  local what="Check allowed actions" st patterns enabled allowed
  st=0
  collect_workflow_uses || st=$?
  if [[ $st -ne 0 ]]; then
    log_step FAIL "$what" "cannot read workflows on ${DEFAULT_BRANCH} ($(collapse "$GH_API_ERROR"))" "pinned-actions"
    return 0
  fi
  patterns=$(non_github_patterns | patterns_json_from_lines)
  if ! gh_api "repos/${SLUG}/actions/permissions"; then
    log_step FAIL "$what" "cannot read Actions permissions ($(collapse "$GH_API_ERROR"))" "pinned-actions"
    return 0
  fi
  enabled=$(jq -r '.enabled // false' <<<"$GH_API_BODY")
  allowed=$(jq -r '.allowed_actions // empty' <<<"$GH_API_BODY")
  if [[ $enabled != true || $allowed != selected ]]; then
    log_step FAIL "$what" "allowed_actions is ${allowed:-unknown}, expected selected (GitHub-owned plus the actions used on ${DEFAULT_BRANCH})" "pinned-actions"
    return 0
  fi
  if ! gh_api "repos/${SLUG}/actions/permissions/selected-actions"; then
    log_step FAIL "$what" "cannot read selected actions ($(collapse "$GH_API_ERROR"))" "pinned-actions"
    return 0
  fi
  if ! selected_actions_match "$patterns"; then
    log_step FAIL "$what" "selected actions do not match workflows on ${DEFAULT_BRANCH}. patterns_allowed applies to public repositories only." "pinned-actions"
    return 0
  fi
  log_step ALREADY "$what" "GitHub-owned actions plus the actions used on ${DEFAULT_BRANCH}" "pinned-actions"
  return 0
}

step_pins() {
  local what="Check actions are pinned to a commit SHA" st list
  st=0
  collect_workflow_uses || st=$?
  if [[ $st -ne 0 ]]; then
    log_step FAIL "$what" "cannot read workflows on ${DEFAULT_BRANCH} ($(collapse "$GH_API_ERROR"))" "pinned-actions"
    return 0
  fi
  list=$(unpinned_uses | paste -sd ', ' -)
  if [[ -z $list ]]; then
    log_step ALREADY "$what" "every uses value is a full commit SHA, or there are none" "pinned-actions"
    return 0
  fi
  log_step OK "$what" "warning: ${list}" "pinned-actions"
  return 0
}

if ! step_gh_version; then
  skip_rest "not run: gh version check failed"
  finish
fi
if ! step_auth; then
  skip_rest "not run: gh auth check failed"
  finish
fi

step_risk_reminder
verify_named_ruleset protect-main protect-main
verify_named_ruleset protect-tags protect-tags
verify_named_ruleset require-checks require-checks
step_agent
step_codeowners
step_token
step_fork
step_actions
step_pins
finish
