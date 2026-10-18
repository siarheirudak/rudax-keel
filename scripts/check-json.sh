#!/usr/bin/env bash
# Every JSON file must parse. The ruleset files must keep the values apply sends.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

fail_file() {
  printf 'how to fix: fix the JSON in %s\n' "$1" >&2
  exit 1
}

while IFS= read -r path; do
  if ! jq empty "$path"; then
    fail_file "$path"
  fi
done < <(find . -name '*.json' -type f -not -path './.git/*' | sort)

if ! jq -e '
  .name == "protect-main"
  and .target == "branch"
  and .enforcement == "active"
  and .conditions.ref_name.include == ["~DEFAULT_BRANCH"]
  and .conditions.ref_name.exclude == []
  and .bypass_actors == [{
    "actor_id": 5,
    "actor_type": "RepositoryRole",
    "bypass_mode": "pull_request"
  }]
  and ([.rules[].type] | sort) == ["deletion", "non_fast_forward", "pull_request"]
  and any(.rules[];
    .type == "pull_request"
    and .parameters.required_approving_review_count == 1
    and .parameters.require_code_owner_review == true
    and .parameters.dismiss_stale_reviews_on_push == true
    and .parameters.require_last_push_approval == false
    and .parameters.required_review_thread_resolution == false
  )
' setup/rulesets/protect-main.json >/dev/null; then
  fail_file "setup/rulesets/protect-main.json"
fi

if ! jq -e '
  .name == "protect-tags"
  and .target == "tag"
  and .enforcement == "active"
  and .conditions.ref_name.include == ["~ALL"]
  and .conditions.ref_name.exclude == []
  and .bypass_actors == [{
    "actor_id": 5,
    "actor_type": "RepositoryRole",
    "bypass_mode": "always"
  }]
  and ([.rules[].type] | sort) == ["creation", "deletion", "update"]
  and any(.rules[]; .type == "update" and .parameters.update_allows_fetch_and_merge == false)
' setup/rulesets/protect-tags.json >/dev/null; then
  fail_file "setup/rulesets/protect-tags.json"
fi

if ! jq -e '
  .name == "require-checks"
  and .target == "branch"
  and .enforcement == "active"
  and .bypass_actors == []
  and .conditions.ref_name.include == ["~DEFAULT_BRANCH"]
  and .conditions.ref_name.exclude == []
  and any(.rules[];
    .type == "required_status_checks"
    and .parameters.strict_required_status_checks_policy == true
    and .parameters.do_not_enforce_on_create == false
    and (.parameters.required_status_checks | sort_by(.context)) == [
      {"context": "checks / gate", "integration_id": 15368},
      {"context": "scope / process-files-separate", "integration_id": 15368}
    ]
  )
' setup/rulesets/require-checks.json >/dev/null; then
  fail_file "setup/rulesets/require-checks.json"
fi
