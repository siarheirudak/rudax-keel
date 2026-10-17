#!/usr/bin/env bash
# Apply GitHub rules for one repository. Idempotent.
# Re-run as the owner GitHub account after each layer merge.
# Settings that already match are left untouched.
# Usage: apply-github-rules.sh OWNER/REPO AGENT_LOGIN [--accept-risk] [--rewrite-codeowners]
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=setup/common.sh
source "$SCRIPT_DIR/common.sh"

positional=()
for arg in "$@"; do
  case $arg in
    --accept-risk) ACCEPT_RISK=1 ;;
    --rewrite-codeowners) REWRITE_CODEOWNERS=1 ;;
    --)
      printf 'Unknown option: %s\n' "$arg" >&2
      usage "apply-github-rules.sh" " [--rewrite-codeowners]"
      ;;
    -*)
      printf 'Unknown option: %s\n' "$arg" >&2
      usage "apply-github-rules.sh" " [--rewrite-codeowners]"
      ;;
    *) positional+=("$arg") ;;
  esac
done
if [[ ${#positional[@]} -ne 2 ]]; then
  usage "apply-github-rules.sh" " [--rewrite-codeowners]"
fi
require_args "apply-github-rules.sh" "${positional[0]}" "${positional[1]}"
init_log "apply"
trap 'on_unexpected $LINENO' ERR

REST_WHAT=(
  "Make CODEOWNERS match the owner GitHub account"
  "Create or update ruleset protect-main"
  "Create or update ruleset protect-tags"
  "Create or update ruleset require-checks"
  "Invite ${AGENT} with write"
  "Set GITHUB_TOKEN permissions to read-only"
  "Require approval for fork pull request workflows"
  "Set allowed actions"
)
REST_ANCHOR=(
  codeowners
  protect-main
  protect-tags
  require-checks
  agent-write-access
  read-only-token
  fork-approval
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
    log_step FAIL "Check gh auth and admin" "$AUTH_ERROR" "who-runs-this"
    return 1
  fi
  log_step OK "Check gh auth and admin" "authenticated as ${LOGIN} with admin on ${SLUG}" "who-runs-this"
  return 0
}

step_risk() {
  local answer
  if [[ $RULESETS_OFF -eq 0 ]]; then
    return 0
  fi
  say "Risk: private repository on GitHub Free. Rulesets are unavailable. The agent GitHub account could push directly to main, with no review. Checks are only advisory. Options: make the repository public, or use GitHub Pro."
  if [[ $ACCEPT_RISK -eq 1 ]]; then
    log_step OK "Accept Free private ruleset risk" "accepted with --accept-risk" "free-private-risk"
    return 0
  fi
  if [[ -t 0 ]]; then
    printf '%s\n' "Type yes to continue:"
    answer=""
    read -r answer || answer=""
    if [[ $answer == yes ]]; then
      log_step OK "Accept Free private ruleset risk" "accepted by typing yes" "free-private-risk"
      return 0
    fi
    log_step FAIL "Accept Free private ruleset risk" "declined" "free-private-risk"
    return 1
  fi
  log_step FAIL "Accept Free private ruleset risk" "not a terminal; re-run with --accept-risk to continue" "free-private-risk"
  return 1
}

apply_named_ruleset() {
  local name=$1 anchor=$2
  local file="$SCRIPT_DIR/rulesets/${name}.json"
  local what="Create or update ruleset ${name}"
  local ids count id st

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
    st=0
    branch_file_status ".github/workflows/checks.yml" || st=$?
    if [[ $st -eq 1 ]]; then
      log_step "NOT YET" "$what" "$CHECKS_SKIP_REASON" "$anchor"
      return 0
    fi
    if [[ $st -ne 0 ]]; then
      log_step FAIL "$what" "cannot read .github/workflows/checks.yml ($(collapse "$GH_API_ERROR"))" "$anchor"
      return 0
    fi
  fi
  if [[ ! -f $file ]]; then
    log_step FAIL "$what" "missing ${file}" "$anchor"
    return 0
  fi
  if ! jq -e . "$file" >/dev/null; then
    log_step FAIL "$what" "${file} is not valid JSON" "$anchor"
    return 0
  fi
  if ! gh_api_collect "repos/${SLUG}/rulesets?includes_parents=false&per_page=100"; then
    log_step FAIL "$what" "cannot list rulesets ($(collapse "$GH_API_ERROR"))" "$anchor"
    return 0
  fi
  ids=$(ruleset_ids "$name")
  count=$(jq -r 'length' <<<"$ids")
  if [[ $count -gt 1 ]]; then
    log_step FAIL "$what" "found ${count} repository rulesets named ${name}; keep one and re-run" "$anchor"
    return 0
  fi
  if [[ $count -eq 0 ]]; then
    if ! gh_api --method POST "repos/${SLUG}/rulesets" --input "$file"; then
      log_step FAIL "$what" "create failed ($(collapse "$GH_API_ERROR"))" "$anchor"
      return 0
    fi
    log_step OK "$what" "created ${name}" "$anchor"
    return 0
  fi
  id=$(jq -r '.[0]' <<<"$ids")
  if ! gh_api "repos/${SLUG}/rulesets/${id}"; then
    log_step FAIL "$what" "cannot read ruleset ${id} ($(collapse "$GH_API_ERROR"))" "$anchor"
    return 0
  fi
  capture_ruleset_diff "$file" "$GH_API_BODY"
  if [[ $DIFF_RC -eq 0 ]]; then
    log_step ALREADY "$what" "already matches setup/rulesets/${name}.json" "$anchor"
    return 0
  fi
  if [[ $DIFF_RC -ne 1 ]]; then
    log_step FAIL "$what" "$(shorten "$DIFF_TEXT")" "$anchor"
    return 0
  fi
  if ! gh_api --method PUT "repos/${SLUG}/rulesets/${id}" --input "$file"; then
    log_step FAIL "$what" "update failed ($(collapse "$GH_API_ERROR"))" "$anchor"
    return 0
  fi
  log_step OK "$what" "updated ${name}" "$anchor"
  return 0
}

step_invite() {
  local what="Invite ${AGENT} with write" perm role pending
  if gh_api "repos/${SLUG}/collaborators/${AGENT}"; then
    if ! gh_api "repos/${SLUG}/collaborators/${AGENT}/permission"; then
      log_step FAIL "$what" "cannot read permission ($(collapse "$GH_API_ERROR"))" "agent-write-access"
      return 0
    fi
    perm=$(jq -r '.permission // empty' <<<"$GH_API_BODY")
    role=$(jq -r '.role_name // empty' <<<"$GH_API_BODY")
    if [[ $perm == admin || $role == admin ]]; then
      log_step FAIL "$what" "role is admin, expected write. Left unchanged." "agent-write-access"
      return 0
    fi
    if [[ $perm == write ]]; then
      log_step ALREADY "$what" "already a collaborator with write" "agent-write-access"
      return 0
    fi
    if ! gh_api --method PUT "repos/${SLUG}/collaborators/${AGENT}" -f permission=push; then
      log_step FAIL "$what" "cannot change role from ${perm:-unknown} ($(collapse "$GH_API_ERROR"))" "agent-write-access"
      return 0
    fi
    log_step OK "$what" "changed role from ${perm:-unknown} to write" "agent-write-access"
    return 0
  fi
  if ! is_not_found; then
    log_step FAIL "$what" "cannot check collaborator ($(collapse "$GH_API_ERROR"))" "agent-write-access"
    return 0
  fi
  if ! gh_api_collect "repos/${SLUG}/invitations"; then
    log_step FAIL "$what" "cannot list invitations ($(collapse "$GH_API_ERROR"))" "agent-write-access"
    return 0
  fi
  pending=$(jq -r --arg login "$AGENT" "$PENDING_INVITE_JQ" <<<"$GH_API_BODY")
  if [[ $pending != 0 ]]; then
    log_step ALREADY "$what" "invitation already pending; the agent GitHub account must accept it" "agent-write-access"
    return 0
  fi
  if ! gh_api --method PUT "repos/${SLUG}/collaborators/${AGENT}" -f permission=push; then
    log_step FAIL "$what" "invite failed ($(collapse "$GH_API_ERROR"))" "agent-write-access"
    return 0
  fi
  log_step OK "$what" "invitation sent with write; the agent GitHub account must accept it" "agent-write-access"
  return 0
}

protect_main_present() {
  local ids count
  if [[ $RULESETS_OFF -eq 1 ]]; then
    printf '0'
    return 0
  fi
  if ! gh_api_collect "repos/${SLUG}/rulesets?includes_parents=false&per_page=100"; then
    return 1
  fi
  ids=$(ruleset_ids "protect-main")
  count=$(jq -r 'length' <<<"$ids")
  if [[ $count -ge 1 ]]; then
    printf '1'
  else
    printf '0'
  fi
}

# The only inherited CODEOWNERS line apply may replace on its own.
TEMPLATE_CODEOWNERS='* @siarheirudak'

codeowners_is_template_value() {
  local text=$1 line saw=0
  while IFS= read -r line || [[ -n $line ]]; do
    line=${line%$'\r'}
    [[ -z $line ]] && continue
    [[ $line == "$TEMPLATE_CODEOWNERS" ]] || return 1
    saw=$((saw + 1))
  done <<<"$text"
  [[ $saw -eq 1 ]]
}

codeowners_keep_reason() {
  printf '%s' "CODEOWNERS does not match * @${LOGIN} and is not the template line ${TEMPLATE_CODEOWNERS}. This script will not rewrite it. Apply still creates protect-main after this FAIL. Open a pull request that sets .github/CODEOWNERS to \`* @${LOGIN}\` and merge it with the admin bypass (pull requests only). Rule Insights is Settings → Rules → Insights. Re-run with --rewrite-codeowners to replace the file, and only before protect-main exists."
}

codeowners_blocked_reason() {
  printf '%s' "protect-main already exists, so this script will not change CODEOWNERS and will not use the admin bypass. Open a pull request that sets .github/CODEOWNERS to \`* @${LOGIN}\` and merge it with the admin bypass (pull requests only). The bypass is logged in Rule Insights (Settings → Rules → Insights)."
}

write_codeowners() {
  local sha=${1-} body
  if [[ -n $sha ]]; then
    body=$(jq -n \
      --arg message "Set CODEOWNERS to the owner GitHub account" \
      --arg content "$(b64_encode "* @${LOGIN}"$'\n')" \
      --arg branch "$DEFAULT_BRANCH" \
      --arg sha "$sha" \
      '{message:$message, content:$content, branch:$branch, sha:$sha}')
  else
    body=$(jq -n \
      --arg message "Set CODEOWNERS to the owner GitHub account" \
      --arg content "$(b64_encode "* @${LOGIN}"$'\n')" \
      --arg branch "$DEFAULT_BRANCH" \
      '{message:$message, content:$content, branch:$branch}')
  fi
  api_put_json "repos/${SLUG}/contents/.github/CODEOWNERS" "$body"
}

step_codeowners() {
  local what="Make CODEOWNERS match the owner GitHub account"
  local st text sha="" present replace=0
  if ! mark_empty_repo; then
    log_step FAIL "$what" "cannot read ${DEFAULT_BRANCH} ($(collapse "$GH_API_ERROR"))" "codeowners"
    return 0
  fi
  if [[ $REPO_EMPTY -eq 1 ]]; then
    log_step FAIL "$what" "repository is empty; push an initial commit to ${DEFAULT_BRANCH}, then re-run" "codeowners"
    return 0
  fi
  if ! present=$(protect_main_present); then
    log_step FAIL "$what" "cannot list rulesets ($(collapse "$GH_API_ERROR"))" "codeowners"
    return 0
  fi
  st=0
  branch_file_status ".github/CODEOWNERS" || st=$?
  if [[ $st -eq 2 ]]; then
    log_step FAIL "$what" "cannot read file ($(collapse "$GH_API_ERROR"))" "codeowners"
    return 0
  fi
  if [[ $st -eq 0 ]]; then
    decode_content_body
    text=$CONTENT_TEXT
    sha=$(jq -r '.sha // empty' <<<"$GH_API_BODY")
    if codeowners_matches "$text"; then
      log_step ALREADY "$what" "already * @${LOGIN}" "codeowners"
      return 0
    fi
    if codeowners_is_template_value "$text" || [[ $REWRITE_CODEOWNERS -eq 1 ]]; then
      replace=1
    elif [[ $present -eq 1 ]]; then
      log_step FAIL "$what" "$(codeowners_blocked_reason)" "codeowners"
      return 0
    else
      log_step FAIL "$what" "$(codeowners_keep_reason)" "codeowners"
      return 0
    fi
  fi
  if [[ $present -eq 1 ]]; then
    log_step FAIL "$what" "$(codeowners_blocked_reason)" "codeowners"
    return 0
  fi
  if [[ $replace -eq 1 ]]; then
    if ! write_codeowners "$sha"; then
      log_step FAIL "$what" "could not write CODEOWNERS ($(collapse "$GH_API_ERROR")). Open a pull request that sets it to \`* @${LOGIN}\` and merge it with the admin bypass (pull requests only). Rule Insights is Settings → Rules → Insights." "codeowners"
      return 0
    fi
    log_step OK "$what" "rewrote CODEOWNERS to * @${LOGIN} on ${DEFAULT_BRANCH}" "codeowners"
    return 0
  fi
  if ! write_codeowners; then
    log_step FAIL "$what" "could not write CODEOWNERS ($(collapse "$GH_API_ERROR")). Open a pull request that sets it to \`* @${LOGIN}\` and merge it with the admin bypass (pull requests only). Rule Insights is Settings → Rules → Insights." "codeowners"
    return 0
  fi
  log_step OK "$what" "created * @${LOGIN} on ${DEFAULT_BRANCH}" "codeowners"
  return 0
}

step_token() {
  local what="Set GITHUB_TOKEN permissions to read-only" perms approve
  if ! gh_api "repos/${SLUG}/actions/permissions/workflow"; then
    log_step FAIL "$what" "cannot read workflow permissions ($(collapse "$GH_API_ERROR"))" "read-only-token"
    return 0
  fi
  perms=$(jq -r '.default_workflow_permissions // empty' <<<"$GH_API_BODY")
  approve=$(jq -r '.can_approve_pull_request_reviews // false' <<<"$GH_API_BODY")
  if [[ $perms == read && $approve == false ]]; then
    log_step ALREADY "$what" "already read-only and cannot approve pull requests" "read-only-token"
    return 0
  fi
  if ! api_put_json "repos/${SLUG}/actions/permissions/workflow" \
    "$(jq -n '{default_workflow_permissions:"read", can_approve_pull_request_reviews:false}')"; then
    log_step FAIL "$what" "update failed ($(collapse "$GH_API_ERROR"))" "read-only-token"
    return 0
  fi
  log_step OK "$what" "set default permissions to read and blocked pull request approval" "read-only-token"
  return 0
}

step_fork() {
  local what="Require approval for fork pull request workflows" policy
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
    log_step ALREADY "$what" "already requires approval for all outside collaborators" "fork-approval"
    return 0
  fi
  if ! api_put_json "repos/${SLUG}/actions/permissions/fork-pr-contributor-approval" \
    "$(jq -n '{approval_policy:"all_external_contributors"}')"; then
    if is_not_found; then
      log_step FAIL "$what" "$FORK_MANUAL_REASON" "fork-approval"
      return 0
    fi
    log_step FAIL "$what" "update failed ($(collapse "$GH_API_ERROR"))" "fork-approval"
    return 0
  fi
  log_step OK "$what" "set approval for all outside collaborators" "fork-approval"
  return 0
}

step_actions() {
  local what="Set allowed actions" st patterns enabled allowed note match
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
  match=0
  if [[ $enabled == true && $allowed == selected ]]; then
    if ! gh_api "repos/${SLUG}/actions/permissions/selected-actions"; then
      log_step FAIL "$what" "cannot read selected actions ($(collapse "$GH_API_ERROR"))" "pinned-actions"
      return 0
    fi
    if selected_actions_match "$patterns"; then
      match=1
    fi
  fi
  if [[ $match -eq 1 ]]; then
    log_step ALREADY "$what" "already GitHub-owned actions plus the actions used on ${DEFAULT_BRANCH}" "pinned-actions"
    return 0
  fi
  if [[ $enabled != true || $allowed != selected ]]; then
    if ! api_put_json "repos/${SLUG}/actions/permissions" \
      "$(jq -n '{enabled:true, allowed_actions:"selected"}')"; then
      log_step FAIL "$what" "cannot set allowed actions to selected ($(collapse "$GH_API_ERROR"))" "pinned-actions"
      return 0
    fi
  fi
  if ! api_put_json "repos/${SLUG}/actions/permissions/selected-actions" \
    "$(jq -n --argjson patterns "$patterns" '{github_owned_allowed:true, verified_allowed:false, patterns_allowed:$patterns}')"; then
    log_step FAIL "$what" "cannot set selected actions ($(collapse "$GH_API_ERROR")). patterns_allowed applies to public repositories." "pinned-actions"
    return 0
  fi
  note="set GitHub-owned actions plus the actions used on ${DEFAULT_BRANCH}"
  if [[ $PRIVATE -eq 1 ]]; then
    note="${note}. patterns_allowed applies to public repositories only"
  fi
  log_step OK "$what" "$note" "pinned-actions"
  return 0
}

if ! step_gh_version; then
  skip_rest "not run: gh version check failed"
  finish
fi
if ! step_auth; then
  skip_rest "not run: caller is not an authenticated admin"
  finish
fi
if ! step_risk; then
  skip_rest "not run: Free private ruleset risk was not accepted"
  finish
fi

step_codeowners
apply_named_ruleset protect-main protect-main
apply_named_ruleset protect-tags protect-tags
apply_named_ruleset require-checks require-checks
step_invite
step_token
step_fork
step_actions
finish
