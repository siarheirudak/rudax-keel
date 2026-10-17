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
CHECKS_SKIP_REASON="CI not added yet; re-run after layer 2 merge"
# shellcheck disable=SC2034
FORK_MANUAL_REASON="API unavailable. Do this by hand: Settings → Actions → General → Fork pull request workflows → Require approval for all outside collaborators."

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
                  | map({context})
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
  printf 'Usage: %s OWNER/REPO AGENT_LOGIN [--accept-risk]\n' "$1" >&2
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
  GH_API_ERROR=$(collapse "${err_text} ${body_text}")
  rm -f "$err_file" "$body_file"
  return 1
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
    "$ACCEPT_RISK" "$REPO_ADMIN" "$CONTENT_TEXT" "$USES_LIST" "$AUTH_ERROR" \
    "$RISK_REASON" "$CHECKS_SKIP_REASON" "$FORK_MANUAL_REASON" "$GH_API_BODY" \
    "$GH_API_ERROR" "$LOG_FILE" "$STEP" "$FAIL_COUNT" "$SUMMARY" "$SLUG" "$AGENT"
}
touch_shared_state
