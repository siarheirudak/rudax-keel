#!/usr/bin/env bash
# Shared logging and GitHub helpers for setup.sh and verify.sh.
# Sourced, not executed.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  printf '%s\n' "source this file from setup.sh or verify.sh" >&2
  exit 1
fi

SCRIPT_DIR=${SCRIPT_DIR:-}
SLUG=${SLUG:-}
AGENT=${AGENT:-}
LOG_FILE=${LOG_FILE:-}
JSON_FILE=${JSON_FILE:-}
STEP=0
FAIL_COUNT=0
SUMMARY=""
GH_API_BODY=""
GH_API_ERROR=""
# Set here and read by setup.sh / verify.sh.
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

# gh --paginate --slurp returns an array of pages. A single page is a plain array.
# shellcheck disable=SC2034
LIST_RULESET_IDS_JQ='
(if type == "array" and length > 0 and (.[0] | type) == "array" then add
 elif type == "array" then .
 else [] end)
| [.[] | select(.name == "protect-main") | select((.source_type // "Repository") == "Repository") | .id]
'

# shellcheck disable=SC2034,SC2016
PENDING_INVITE_JQ='
(if type == "array" and length > 0 and (.[0] | type) == "array" then add
 elif type == "array" then .
 else [] end)
| [.[] | select((.invitee.login // "" | ascii_downcase) == ($login | ascii_downcase))]
| length
'

# Normalize a ruleset down to the fields protect-main.json is responsible for.
# Extra API fields (id, links, allowed_merge_methods, current_user_can_bypass)
# are ignored. Missing booleans are treated as false.
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
  printf 'Usage: %s OWNER/REPO AGENT_LOGIN\n' "$1" >&2
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
  OWNER=${SLUG%%/*}
  JSON_FILE=$SCRIPT_DIR/rulesets/protect-main.json
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
  local line now short
  STEP=$((STEP + 1))
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if [[ -n $reason ]]; then
    line="${STEP} [${now}] ${what} - ${status}: ${reason}"
    short="${STEP} ${status} - ${what}: ${reason}"
  else
    line="${STEP} [${now}] ${what} - ${status}"
    short="${STEP} ${status} - ${what}"
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
  log_step FAIL "Unexpected error" "script stopped at line ${line}"
  finish
}

skip_remaining() {
  local reason=$1
  shift
  local what
  for what in "$@"; do
    log_step FAIL "$what" "$reason"
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

# Print "match", a one-line diff, or an error.
# Return 0 on match, 1 when the ruleset differs, 2 when comparison itself fails.
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

codeowners_hint() {
  printf "create .github/CODEOWNERS containing '* @%s' in the owner's own pull request and merge it with the admin bypass (pull requests only). This script does not create the file." "$OWNER"
}
