#!/usr/bin/env bash
# Shared helpers for apply-github-rules.sh and verify-github-rules.sh.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  printf '%s\n' "source this file from apply-github-rules.sh or verify-github-rules.sh" >&2
  exit 1
fi

SCRIPT_DIR=${SCRIPT_DIR:-}
SLUG=${SLUG:-}
AGENT=${AGENT:-}
LOG_FILE=${LOG_FILE:-}
STEP=0
FAIL_COUNT=0
SUMMARY=""
GH_API_BODY=""
GH_API_ERROR=""
# shellcheck disable=SC2034
LOGIN=""
# shellcheck disable=SC2034
DEFAULT_BRANCH=""
# shellcheck disable=SC2034
REPO_EMPTY=0
# shellcheck disable=SC2034
DIFF_RC=0
# shellcheck disable=SC2034
DIFF_TEXT=""
# shellcheck disable=SC2034
RULESETS_OFF=0
# shellcheck disable=SC2034
PRIVATE=0
# shellcheck disable=SC2034
PLAN=""
# shellcheck disable=SC2034
REPO_OWNER=""
# shellcheck disable=SC2034
OWNER_TYPE=""
# shellcheck disable=SC2034
ACCEPT_RISK=0
# shellcheck disable=SC2034
REWRITE_CODEOWNERS=0
# shellcheck disable=SC2034
REPO_ADMIN=false
# shellcheck disable=SC2034
CONTENT_TEXT=""
# shellcheck disable=SC2034
USES_LIST=""
# shellcheck disable=SC2034
AUTH_ERROR=""
# shellcheck disable=SC2034
RISK_REASON="GitHub Free on a private repository has no rulesets. The agent GitHub account could push directly to main, there is no review, and checks are only advisory. Make the repository public or use GitHub Pro."
# shellcheck disable=SC2034
CHECKS_SKIP_REASON="waiting for checks.yml and scope.yml on the default branch, and for checks / gate and scope / process-files-separate to have reported at least once"
OWNER_APPLY_REASON="owner: run setup/apply-github-rules.sh"
REQUIRE_CHECKS_FILES=0
REQUIRE_CHECKS_REPORTED=0
WORKFLOW_REPORTED=0
CHECKS_RED=0
CHECKS_CONCLUSION=""
# shellcheck disable=SC2034
FORK_MANUAL_REASON="API unavailable. Do this by hand: Settings → Actions → General → Fork pull request workflows → Require approval for all outside collaborators."
# gh api --jq arrived in 1.7.0. --paginate, --input, --method, and -f are older.
# shellcheck disable=SC2034
MIN_GH_VERSION=1.7.0

# shellcheck disable=SC2034,SC2016
PENDING_INVITE_JQ='
(if type == "array" and length > 0 and (.[0] | type) == "array" then add
 elif type == "array" then .
 else [] end)
| [.[] | select((.invitee.login // "" | ascii_downcase) == ($login | ascii_downcase))]
| length
'

# Compare the fields these JSON files define. Extra API fields are ignored.
# shellcheck disable=SC2016
RULESET_JQ='
def flag(v): if v == null then false else v end;
def norm:
  {
    name: .name,
    target: (.target // "branch"),
    enforcement: .enforcement,
    include: ((.conditions.ref_name.include // []) | sort),
    exclude: ((.conditions.ref_name.exclude // []) | sort),
    bypass: (
      (.bypass_actors // [])
      | map({actor_id, actor_type, bypass_mode})
      | sort_by(.actor_type, (.actor_id // -1), (.bypass_mode // ""))
    ),
    rules: (
      (.rules // [])
      | map(
          if .type == "pull_request" then
            {
              type,
              parameters: {
                required_approving_review_count: .parameters.required_approving_review_count,
                require_code_owner_review: flag(.parameters.require_code_owner_review),
                dismiss_stale_reviews_on_push: flag(.parameters.dismiss_stale_reviews_on_push),
                require_last_push_approval: flag(.parameters.require_last_push_approval),
                required_review_thread_resolution: flag(.parameters.required_review_thread_resolution)
              }
            }
          elif .type == "required_status_checks" then
            {
              type,
              parameters: {
                strict_required_status_checks_policy: flag(.parameters.strict_required_status_checks_policy),
                do_not_enforce_on_create: flag(.parameters.do_not_enforce_on_create),
                required_status_checks: (
                  (.parameters.required_status_checks // [])
                  | map({context, integration_id: (.integration_id // null)})
                  | sort_by(.context)
                )
              }
            }
          elif .type == "update" then
            {
              type,
              parameters: {
                update_allows_fetch_and_merge: flag(.parameters.update_allows_fetch_and_merge)
              }
            }
          else {type, parameters: {}}
          end
        )
      | sort_by(.type // "")
    )
  };
($expected[0] | norm) as $e
| ($actual | norm) as $a
| if $e == $a then "match"
  else "expected " + ($e | tojson) + " actual " + ($a | tojson)
  end
'

usage() {
  printf 'Usage: %s OWNER/REPO AGENT_LOGIN [--accept-risk]%s\n' "$1" "${2-}" >&2
  exit 2
}

require_args() {
  local name=$1
  if [[ $# -ne 3 ]]; then
    usage "$name"
  fi
  SLUG=$2
  AGENT=$3
  if [[ ! $SLUG =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
    printf 'OWNER/REPO must look like owner/repo, got: %s\n' "$SLUG" >&2
    exit 2
  fi
  if [[ -z $AGENT || $AGENT == */* || $AGENT == -* ]]; then
    printf 'AGENT_LOGIN is invalid: %s\n' "$AGENT" >&2
    exit 2
  fi
  REPO_OWNER=${SLUG%%/*}
}

collapse() {
  local text=$1
  text=${text//$'\n'/ }
  text=${text//$'\r'/ }
  printf '%s' "$text" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//'
}

say() {
  printf '%s\n' "$1" | tee -a "$LOG_FILE"
}

log_step() {
  local status=$1
  local what=$2
  local reason=${3-}
  local anchor=${4-}
  local line now short docs
  docs=""
  if [[ -n $anchor ]]; then
    docs=" (docs/why.md#${anchor})"
  fi
  STEP=$((STEP + 1))
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if [[ -n $reason ]]; then
    line="${STEP} [${now}] ${what} - ${status}: ${reason}${docs}"
    short="${STEP} ${status} - ${what}: ${reason}${docs}"
  else
    line="${STEP} [${now}] ${what} - ${status}${docs}"
    short="${STEP} ${status} - ${what}${docs}"
  fi
  say "$line"
  SUMMARY="${SUMMARY}${short}"$'\n'
  if [[ $status == FAIL ]]; then
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

init_log() {
  local prefix=$1
  local dir stamp
  dir=${SETUP_LOG_DIR:-$SCRIPT_DIR/logs}
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  mkdir -p "$dir"
  LOG_FILE="${dir}/${prefix}-${stamp}.log"
  {
    printf 'script: %s\n' "$prefix"
    printf 'args: %s %s\n' "$SLUG" "$AGENT"
    printf 'started: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'accept_risk_flag: %s\n' "$ACCEPT_RISK"
    printf 'rewrite_codeowners_flag: %s\n' "$REWRITE_CODEOWNERS"
  } >"$LOG_FILE"
  say "Log: ${LOG_FILE}"
}

finish() {
  say "Summary"
  if [[ -n $SUMMARY ]]; then
    printf '%s' "$SUMMARY" | tee -a "$LOG_FILE"
  fi
  say "Result: ${STEP} steps, ${FAIL_COUNT} FAIL"
  say "Log: ${LOG_FILE}"
  if [[ "$FAIL_COUNT" -gt 0 ]]; then
    exit 1
  fi
  exit 0
}

on_unexpected() {
  local line=$1
  trap - ERR
  log_step FAIL "Unexpected error" "script stopped at line ${line}" "who-runs-this"
  finish
}

skip_remaining() {
  local reason=$1
  shift
  local what anchor
  while [[ $# -ge 2 ]]; do
    what=$1
    anchor=$2
    shift 2
    log_step FAIL "$what" "$reason" "$anchor"
  done
}

# First useful line only. gh prints its whole usage page after "unknown flag".
gh_error_line() {
  local err=$1 body=$2 line msg=""
  while IFS= read -r line || [[ -n $line ]]; do
    line=${line%$'\r'}
    [[ -z $line ]] && continue
    case $line in
      Usage:*|usage:*|USAGE:*|Flags:*) continue ;;
      "  "*|"-"*) continue ;;
    esac
    msg=$line
    break
  done <<<"$err"
  if [[ -z $msg ]]; then
    msg=$(jq -r '.message // empty' <<<"$body" 2>/dev/null || true)
  fi
  if [[ -z $msg ]]; then
    msg="gh failed"
  fi
  collapse "$msg"
}

gh_api() {
  local err_file body_file err_text body_text
  err_file=$(mktemp)
  body_file=$(mktemp)
  GH_API_BODY=""
  GH_API_ERROR=""
  if gh api "$@" >"$body_file" 2>"$err_file"; then
    GH_API_BODY=$(cat "$body_file")
    rm -f "$err_file" "$body_file"
    return 0
  fi
  err_text=$(cat "$err_file")
  body_text=$(cat "$body_file")
  GH_API_BODY=$body_text
  GH_API_ERROR=$(gh_error_line "$err_text" "$body_text")
  rm -f "$err_file" "$body_file"
  return 1
}

# List every page as one JSON array. --jq '.[]' works on gh 1.7.0 and later.
# --slurp does not: that flag needs gh 2.48.0.
gh_api_collect() {
  local err_file body_file err_text body_text
  err_file=$(mktemp)
  body_file=$(mktemp)
  GH_API_BODY=""
  GH_API_ERROR=""
  if gh api --paginate --jq '.[]' "$@" >"$body_file" 2>"$err_file"; then
    if ! GH_API_BODY=$(jq -s '.' <"$body_file" 2>"$err_file"); then
      GH_API_ERROR=$(gh_error_line "$(cat "$err_file")" "")
      rm -f "$err_file" "$body_file"
      return 1
    fi
    rm -f "$err_file" "$body_file"
    return 0
  fi
  err_text=$(cat "$err_file")
  body_text=$(cat "$body_file")
  GH_API_BODY=$body_text
  GH_API_ERROR=$(gh_error_line "$err_text" "$body_text")
  rm -f "$err_file" "$body_file"
  return 1
}

gh_cli_version() {
  local text line
  text=$(gh --version 2>/dev/null) || return 1
  line=${text%%$'\n'*}
  if [[ $line =~ gh[[:space:]]version[[:space:]]([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
    printf '%s' "${BASH_REMATCH[1]}.${BASH_REMATCH[2]}.${BASH_REMATCH[3]}"
    return 0
  fi
  return 1
}

version_at_least() {
  local have=$1 need=$2
  local have_major have_minor have_patch
  local need_major need_minor need_patch
  IFS=. read -r have_major have_minor have_patch <<<"$have"
  IFS=. read -r need_major need_minor need_patch <<<"$need"
  have_major=${have_major:-0}
  have_minor=${have_minor:-0}
  have_patch=${have_patch:-0}
  need_major=${need_major:-0}
  need_minor=${need_minor:-0}
  need_patch=${need_patch:-0}
  have_patch=${have_patch%%[^0-9]*}
  need_patch=${need_patch%%[^0-9]*}
  if ((10#$have_major > 10#$need_major)); then return 0; fi
  if ((10#$have_major < 10#$need_major)); then return 1; fi
  if ((10#$have_minor > 10#$need_minor)); then return 0; fi
  if ((10#$have_minor < 10#$need_minor)); then return 1; fi
  ((10#$have_patch >= 10#$need_patch))
}

step_gh_version() {
  local what="Check gh version" ver
  if ! command -v gh >/dev/null 2>&1; then
    log_step FAIL "$what" "gh is not on PATH. Install gh ${MIN_GH_VERSION} or newer: https://cli.github.com/" "gh-version"
    return 1
  fi
  if ! ver=$(gh_cli_version); then
    log_step FAIL "$what" "could not read gh version. Install gh ${MIN_GH_VERSION} or newer: https://cli.github.com/" "gh-version"
    return 1
  fi
  if ! version_at_least "$ver" "$MIN_GH_VERSION"; then
    log_step FAIL "$what" "gh ${ver} is older than ${MIN_GH_VERSION}. Upgrade gh: https://cli.github.com/ . Needed: gh api --paginate and gh api --jq." "gh-version"
    return 1
  fi
  log_step OK "$what" "gh ${ver}" "gh-version"
  return 0
}

api_blob() {
  printf '%s\n%s\n' "$GH_API_BODY" "$GH_API_ERROR"
}

is_not_found() {
  api_blob | grep -qi 'not found'
}

is_empty_repo() {
  api_blob | grep -qi 'empty'
}

is_plan_block() {
  api_blob | grep -Eqi 'upgrade|billing|github pro|not available|ruleset'
}

ruleset_ids() {
  jq -c --arg name "$1" '
    (if type == "array" and length > 0 and (.[0] | type) == "array" then add
     elif type == "array" then .
     else [] end)
    | [.[] | select(.name == $name) | select((.source_type // "Repository") == "Repository") | .id]
  ' <<<"$GH_API_BODY"
}

ruleset_diff() {
  local expected_file=$1
  local actual_json=$2
  local out
  if ! out=$(jq -nr --slurpfile expected "$expected_file" --argjson actual "$actual_json" "$RULESET_JQ" 2>&1); then
    printf '%s' "could not compare ruleset JSON: $(collapse "$out")"
    return 2
  fi
  if [[ $out == match ]]; then
    printf '%s' "match"
    return 0
  fi
  printf '%s' "$out"
  return 1
}

capture_ruleset_diff() {
  # shellcheck disable=SC2034
  DIFF_RC=0
  # shellcheck disable=SC2034
  DIFF_TEXT=$(ruleset_diff "$1" "$2") || DIFF_RC=$?
}

b64_decode() {
  local data=$1 out
  if out=$(printf '%s' "$data" | base64 -d 2>/dev/null); then
    printf '%s' "$out"
    return 0
  fi
  if out=$(printf '%s' "$data" | base64 -D 2>/dev/null); then
    printf '%s' "$out"
    return 0
  fi
  printf '%s' ""
}

b64_encode() {
  printf '%s' "$1" | base64 | tr -d '\n'
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

codeowners_lists_login() {
  local text=$1 login_lc line owner
  login_lc=$(lower "$LOGIN")
  while IFS= read -r line || [[ -n $line ]]; do
    case $line in
      ''|\#*) continue ;;
    esac
    set -f
    # shellcheck disable=SC2086
    set -- $line
    set +f
    [[ ${1-} == '*' ]] || continue
    shift
    for owner in "$@"; do
      owner=$(lower "${owner#@}")
      if [[ $owner == "$login_lc" ]]; then
        return 0
      fi
    done
  done <<<"$text"
  return 1
}

# 0 when the only owner line is "* @LOGIN" (blank lines and comments allowed).
codeowners_matches() {
  local text=$1 login_lc line owner saw=0
  login_lc=$(lower "$LOGIN")
  while IFS= read -r line || [[ -n $line ]]; do
    case $line in
      ''|\#*) continue ;;
    esac
    set -f
    # shellcheck disable=SC2086
    set -- $line
    set +f
    [[ ${1-} == '*' ]] || return 1
    shift
    [[ $# -eq 1 ]] || return 1
    owner=$(lower "${1#@}")
    [[ $owner == "$login_lc" ]] || return 1
    saw=1
  done <<<"$text"
  [[ $saw -eq 1 ]]
}

load_repo_fields() {
  local priv
  priv=$(jq -r '.private // false' <<<"$GH_API_BODY")
  if [[ $priv == true ]]; then
    PRIVATE=1
  else
    PRIVATE=0
  fi
  OWNER_TYPE=$(jq -r '.owner.type // "User"' <<<"$GH_API_BODY")
  DEFAULT_BRANCH=$(jq -r '.default_branch // empty' <<<"$GH_API_BODY")
  REPO_ADMIN=$(jq -r '.permissions.admin // false' <<<"$GH_API_BODY")
}

refresh_plan() {
  local org_plan caller_plan
  caller_plan=$PLAN
  if [[ $OWNER_TYPE == Organization ]]; then
    PLAN=""
    if gh_api "orgs/${REPO_OWNER}"; then
      org_plan=$(jq -r '.plan.name // empty' <<<"$GH_API_BODY")
      PLAN=$org_plan
    fi
    return 0
  fi
  # A user-owned repo uses that user's plan, not a collaborator's plan.
  if [[ $(lower "$LOGIN") != $(lower "$REPO_OWNER") ]]; then
    PLAN=""
    return 0
  fi
  PLAN=$caller_plan
}

detect_ruleset_access() {
  local plan_lc
  RULESETS_OFF=0
  plan_lc=$(lower "$PLAN")
  if [[ $PRIVATE -eq 0 ]]; then
    return 0
  fi
  if [[ $plan_lc == free ]]; then
    RULESETS_OFF=1
    return 0
  fi
  if [[ -n $plan_lc ]]; then
    return 0
  fi
  if gh_api "repos/${SLUG}/rulesets?includes_parents=false&per_page=1"; then
    return 0
  fi
  if is_plan_block; then
    RULESETS_OFF=1
  fi
  return 0
}

prepare_auth() {
  local login_lc agent_lc
  AUTH_ERROR=""
  if ! command -v gh >/dev/null 2>&1; then
    AUTH_ERROR="gh is not on PATH"
    return 1
  fi
  if ! command -v jq >/dev/null 2>&1; then
    AUTH_ERROR="jq is not on PATH"
    return 1
  fi
  if ! gh_api user; then
    AUTH_ERROR="gh is not authenticated ($(collapse "$GH_API_ERROR")). Run gh auth login as the owner GitHub account."
    return 1
  fi
  LOGIN=$(jq -r '.login // empty' <<<"$GH_API_BODY") || {
    AUTH_ERROR="gh user response was not JSON"
    return 1
  }
  PLAN=$(jq -r '.plan.name // empty' <<<"$GH_API_BODY") || PLAN=""
  if [[ -z $LOGIN ]]; then
    AUTH_ERROR="gh user response had no login"
    return 1
  fi
  login_lc=$(lower "$LOGIN")
  agent_lc=$(lower "$AGENT")
  if [[ $login_lc == "$agent_lc" ]]; then
    AUTH_ERROR="authenticated as the agent GitHub account ${LOGIN}. Use the owner GitHub account. Never use the agent's token."
    return 1
  fi
  if ! gh_api "repos/${SLUG}"; then
    AUTH_ERROR="cannot read ${SLUG} ($(collapse "$GH_API_ERROR"))"
    return 1
  fi
  load_repo_fields
  if [[ $REPO_ADMIN != true ]]; then
    AUTH_ERROR="authenticated as ${LOGIN} without admin on ${SLUG}"
    return 1
  fi
  if [[ -z $DEFAULT_BRANCH ]]; then
    AUTH_ERROR="repository ${SLUG} has no default branch"
    return 1
  fi
  refresh_plan
  detect_ruleset_access
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

require_checks_files_ready() {
  local st_checks=0 st_scope=0
  REQUIRE_CHECKS_FILES=0
  branch_file_status ".github/workflows/checks.yml" || st_checks=$?
  if [[ $st_checks -eq 2 ]]; then
    REQUIRE_CHECKS_FILES=2
    return 0
  fi
  branch_file_status ".github/workflows/scope.yml" || st_scope=$?
  if [[ $st_scope -eq 2 ]]; then
    REQUIRE_CHECKS_FILES=2
    return 0
  fi
  if [[ $st_checks -eq 0 && $st_scope -eq 0 ]]; then
    REQUIRE_CHECKS_FILES=1
  fi
}

workflow_reported() {
  local file=$1 count
  WORKFLOW_REPORTED=0
  if ! gh_api "repos/${SLUG}/actions/workflows/${file}/runs?per_page=1"; then
    if is_not_found; then
      return 0
    fi
    return 2
  fi
  count=$(jq -r '.total_count // 0' <<<"$GH_API_BODY")
  if [[ $count -gt 0 ]]; then
    WORKFLOW_REPORTED=1
  fi
}

require_checks_reported() {
  REQUIRE_CHECKS_REPORTED=0
  workflow_reported "checks.yml" || return 2
  if [[ $WORKFLOW_REPORTED -ne 1 ]]; then
    return 0
  fi
  workflow_reported "scope.yml" || return 2
  if [[ $WORKFLOW_REPORTED -eq 1 ]]; then
    REQUIRE_CHECKS_REPORTED=1
  fi
}

latest_checks_is_red() {
  CHECKS_RED=0
  CHECKS_CONCLUSION=""
  if ! gh_api "repos/${SLUG}/actions/workflows/checks.yml/runs?per_page=1&branch=${DEFAULT_BRANCH}"; then
    return 0
  fi
  CHECKS_CONCLUSION=$(jq -r '(.workflow_runs // [])[0].conclusion // empty' <<<"$GH_API_BODY")
  case $CHECKS_CONCLUSION in
    failure|cancelled|timed_out|startup_failure) CHECKS_RED=1 ;;
  esac
}

warn_if_checks_red() {
  latest_checks_is_red || true
  if [[ $CHECKS_RED -eq 1 ]]; then
    log_step WARN "Latest checks run on ${DEFAULT_BRANCH}" "conclusion is ${CHECKS_CONCLUSION}" "require-checks"
  fi
}

branch_file_status() {
  local path=$1
  if gh_api --method GET "repos/${SLUG}/contents/${path}" -f "ref=${DEFAULT_BRANCH}"; then
    return 0
  fi
  if is_not_found; then
    return 1
  fi
  return 2
}

decode_content_body() {
  local encoded
  encoded=$(jq -r '.content // empty' <<<"$GH_API_BODY" | tr -d '\n ')
  CONTENT_TEXT=$(b64_decode "$encoded")
}

extract_uses_from_text() {
  local line rest
  while IFS= read -r line || [[ -n $line ]]; do
    [[ $line == *uses:* ]] || continue
    [[ $line =~ ^[[:space:]]*# ]] && continue
    rest=${line#*uses:}
    rest=${rest#"${rest%%[![:space:]]*}"}
    rest=${rest%%[[:space:]]*}
    rest=${rest#\"}
    rest=${rest%\"}
    rest=${rest#\'}
    rest=${rest%\'}
    [[ -n $rest ]] || continue
    printf '%s\n' "$rest"
  done
}

collect_workflow_uses() {
  local st names name uses_line
  USES_LIST=""
  st=0
  branch_file_status ".github/workflows" || st=$?
  if [[ $st -eq 1 ]]; then
    return 0
  fi
  if [[ $st -eq 2 ]]; then
    return 2
  fi
  names=$(jq -r 'if type == "array" then .[] | select(.type == "file") | .name else empty end' <<<"$GH_API_BODY") || return 2
  while IFS= read -r name; do
    [[ -n $name ]] || continue
    case $name in
      *.yml|*.yaml) ;;
      *) continue ;;
    esac
    st=0
    branch_file_status ".github/workflows/${name}" || st=$?
    if [[ $st -ne 0 ]]; then
      return 2
    fi
    decode_content_body
    while IFS= read -r uses_line; do
      [[ -n $uses_line ]] || continue
      USES_LIST+="${uses_line}"$'\n'
    done < <(printf '%s\n' "$CONTENT_TEXT" | extract_uses_from_text)
  done <<<"$names"
  return 0
}

use_skipped() {
  case $1 in
    ./*|docker://*) return 0 ;;
    *) return 1 ;;
  esac
}

use_is_pinned() {
  local ref=${1##*@}
  [[ $1 == *@* ]] || return 1
  [[ $ref =~ ^[0-9a-fA-F]{40}$ ]]
}

use_is_github_owned() {
  local path=${1%%@*} owner
  owner=${path%%/*}
  [[ $owner == actions || $owner == github ]]
}

non_github_patterns() {
  local line
  while IFS= read -r line; do
    [[ -n $line ]] || continue
    use_skipped "$line" && continue
    use_is_github_owned "$line" && continue
    printf '%s\n' "$line"
  done <<<"$USES_LIST" | sort -u
}

unpinned_uses() {
  local line
  while IFS= read -r line; do
    [[ -n $line ]] || continue
    use_skipped "$line" && continue
    if ! use_is_pinned "$line"; then
      printf '%s\n' "$line"
    fi
  done <<<"$USES_LIST" | sort -u
}

# shellcheck disable=SC2016
patterns_json_from_lines() {
  jq -Rsc 'split("\n") | map(select(length > 0)) | unique | sort'
}


shorten() {
  local text=$1
  if [[ ${#text} -gt 500 ]]; then
    printf '%s' "${text:0:500}..."
    return 0
  fi
  printf '%s' "$text"
}

selected_actions_match() {
  local patterns_json=$1 actual want
  actual=$(jq -c '{github_owned_allowed: (.github_owned_allowed // false), verified_allowed: (.verified_allowed // false), patterns_allowed: ((.patterns_allowed // []) | sort)}' <<<"$GH_API_BODY") || return 2
  want=$(jq -nc --argjson patterns "$patterns_json" '{github_owned_allowed:true, verified_allowed:false, patterns_allowed:$patterns}') || return 2
  [[ $actual == "$want" ]]
}

api_put_json() {
  local path=$1 payload=$2 file status=1
  file=$(mktemp)
  printf '%s' "$payload" >"$file"
  if gh_api --method PUT "$path" --input "$file"; then
    status=0
  else
    status=$?
  fi
  rm -f "$file"
  return "$status"
}

# Read by apply-github-rules.sh and verify-github-rules.sh after sourcing.
touch_shared_state() {
  : "$LOGIN" "$DEFAULT_BRANCH" "$REPO_EMPTY" "$DIFF_RC" "$DIFF_TEXT" \
    "$RULESETS_OFF" "$PRIVATE" "$PLAN" "$REPO_OWNER" "$OWNER_TYPE" \
    "$ACCEPT_RISK" "$REWRITE_CODEOWNERS" "$REPO_ADMIN" "$CONTENT_TEXT" "$USES_LIST" "$AUTH_ERROR" \
    "$RISK_REASON" "$CHECKS_SKIP_REASON" "$OWNER_APPLY_REASON" "$FORK_MANUAL_REASON" "$MIN_GH_VERSION" "$GH_API_BODY" \
    "$REQUIRE_CHECKS_FILES" "$REQUIRE_CHECKS_REPORTED" "$WORKFLOW_REPORTED" "$CHECKS_RED" "$CHECKS_CONCLUSION" \
    "$GH_API_ERROR" "$LOG_FILE" "$STEP" "$FAIL_COUNT" "$SUMMARY" "$SLUG" "$AGENT"
}
touch_shared_state
