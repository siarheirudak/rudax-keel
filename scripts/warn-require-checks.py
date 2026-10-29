#!/usr/bin/env python3
"""Remind the owner to apply require-checks. Never fails the job.

On a pull request, if keel-gate and keel-process-files-separate have both
been reported by GitHub Actions app 15368 and no active ruleset named
require-checks exists, print a GitHub Actions warning. A permissions error
from the default token prints a notice and skips the reminder. --self-test
checks that decision with no network.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

APP_ID = 15368
CONTEXTS = ("keel-gate", "keel-process-files-separate")
WARNING = (
    "keel-gate and keel-process-files-separate have reported, but no active "
    "ruleset named require-checks exists. Run setup/apply-github-rules.sh."
)
NOTICE_RULES = (
    "could not read rulesets with the default token; skipping the require-checks reminder"
)
NOTICE_CHECKS = "could not read check runs; skipping the require-checks reminder"
DENIED = {401, 403, 429}


def decide(rules_state, rulesets, reported):
    """Return (kind, text). kind is ok, notice, or warning."""
    if rules_state == "denied":
        return "notice", NOTICE_RULES
    if rules_state != "ok":
        return "notice", NOTICE_RULES
    if has_active_require_checks(rulesets):
        return "ok", ""
    if not isinstance(reported, set):
        return "notice", NOTICE_CHECKS
    if all(name in reported for name in CONTEXTS):
        return "warning", WARNING
    return "ok", ""


def has_active_require_checks(rulesets):
    if not isinstance(rulesets, list):
        return False
    for item in rulesets:
        if not isinstance(item, dict):
            continue
        if item.get("name") == "require-checks" and item.get("enforcement") == "active":
            return True
    return False


def workflow_command(kind, text):
    if kind not in ("notice", "warning") or not text:
        return ""
    safe = (
        text.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )
    return "::{0}::{1}".format(kind, safe)


def emit(kind, text):
    command = workflow_command(kind, text)
    if command:
        print(command)


def github_get(url, token):
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "rudax-keel-require-checks",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return response.status, None
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError, OSError):
        return 0, None


def read_rulesets(repo, token):
    found = []
    for page in range(1, 6):
        url = (
            "https://api.github.com/repos/{0}/rulesets?includes_parents=false&per_page=100&page={1}".format(
                repo, page
            )
        )
        status, body = github_get(url, token)
        if status in DENIED or status == 0:
            return "denied", []
        if status != 200 or not isinstance(body, list):
            return "error", []
        found.extend(body)
        if len(body) < 100:
            break
    return "ok", found


def check_reported(repo, token, sha, name):
    if not sha or any(char not in "0123456789abcdef" for char in sha.lower()):
        return False
    quoted = urllib.parse.quote(name, safe="")
    url = (
        "https://api.github.com/repos/{0}/commits/{1}/check-runs?check_name={2}&app_id={3}&per_page=20".format(
            repo, sha, quoted, APP_ID
        )
    )
    status, body = github_get(url, token)
    if status in DENIED or status == 0:
        return None
    if status == 404:
        return False
    if status != 200 or not isinstance(body, dict):
        return None
    runs = body.get("check_runs") or []
    if not isinstance(runs, list):
        return None
    for item in runs:
        if not isinstance(item, dict):
            continue
        app = item.get("app") or {}
        if item.get("name") == name and app.get("id") == APP_ID:
            return True
    return False


def collect_reported(repo, token):
    found = set()
    wanted = set(CONTEXTS)
    for workflow in ("checks.yml", "scope.yml"):
        if wanted <= found:
            return found
        for page in (1, 2):
            if wanted <= found:
                return found
            url = (
                "https://api.github.com/repos/{0}/actions/workflows/{1}/runs?per_page=20&page={2}".format(
                    repo, workflow, page
                )
            )
            status, body = github_get(url, token)
            if status == 404:
                break
            if status in DENIED or status == 0 or status != 200 or not isinstance(body, dict):
                return None
            runs = body.get("workflow_runs") or []
            if not isinstance(runs, list):
                return None
            for run in runs:
                if not isinstance(run, dict):
                    continue
                if wanted <= found:
                    return found
                sha = run.get("head_sha") or ""
                run_id = run.get("id")
                if not isinstance(run_id, int):
                    continue
                jobs_url = (
                    "https://api.github.com/repos/{0}/actions/runs/{1}/jobs?per_page=100&page=1".format(
                        repo, run_id
                    )
                )
                jobs_status, jobs_body = github_get(jobs_url, token)
                if jobs_status == 404:
                    continue
                if (
                    jobs_status in DENIED
                    or jobs_status == 0
                    or jobs_status != 200
                    or not isinstance(jobs_body, dict)
                ):
                    return None
                jobs = jobs_body.get("jobs") or []
                if not isinstance(jobs, list):
                    return None
                for job in jobs:
                    if not isinstance(job, dict):
                        continue
                    name = job.get("name") or ""
                    if name not in wanted or name in found:
                        continue
                    seen = check_reported(repo, token, sha, name)
                    if seen is None:
                        return None
                    if seen:
                        found.add(name)
            if len(runs) < 20:
                break
    return found


def live_outcome():
    repo = os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY") or ""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if "/" not in repo or not token or ".." in repo.split("/"):
        return "notice", NOTICE_RULES
    rules_state, rulesets = read_rulesets(repo, token)
    if rules_state != "ok":
        return decide(rules_state, rulesets, None)
    if has_active_require_checks(rulesets):
        return "ok", ""
    return decide(rules_state, rulesets, collect_reported(repo, token))


def self_test():
    both = set(CONTEXTS)
    cases = [
        ("denied", [], None, "notice", NOTICE_RULES),
        ("error", [], both, "notice", NOTICE_RULES),
        (
            "ok",
            [{"name": "require-checks", "enforcement": "active"}],
            both,
            "ok",
            "",
        ),
        (
            "ok",
            [{"name": "require-checks", "enforcement": "disabled"}],
            both,
            "warning",
            WARNING,
        ),
        ("ok", [{"name": "protect-main", "enforcement": "active"}], both, "warning", WARNING),
        ("ok", [], {"keel-gate"}, "ok", ""),
        ("ok", [], None, "notice", NOTICE_CHECKS),
        ("ok", "not-a-list", both, "warning", WARNING),
    ]
    for rules_state, rulesets, reported, kind, text in cases:
        got_kind, got_text = decide(rules_state, rulesets, reported)
        if got_kind != kind or got_text != text:
            print(
                "self-test mismatch state={0} kind={1} text={2}".format(
                    rules_state, got_kind, got_text
                ),
                file=sys.stderr,
            )
            print(
                "how to fix: fix the require-checks reminder in scripts/warn-require-checks.py",
                file=sys.stderr,
            )
            return 1
        if got_kind == "warning" and "setup/apply-github-rules.sh" not in got_text:
            print("self-test warning missing the setup command", file=sys.stderr)
            return 1
        command = workflow_command(got_kind, got_text)
        if got_kind == "ok" and command:
            print("self-test emitted a command for an ok result", file=sys.stderr)
            return 1
        if got_kind == "warning" and not command.startswith("::warning::"):
            print("self-test warning command was {0}".format(command), file=sys.stderr)
            return 1
        if got_kind == "notice" and not command.startswith("::notice::"):
            print("self-test notice command was {0}".format(command), file=sys.stderr)
            return 1
    if has_active_require_checks([{"name": "require-checks", "enforcement": "evaluate"}]):
        print("self-test treated evaluate as active", file=sys.stderr)
        return 1
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    try:
        kind, text = live_outcome()
        emit(kind, text)
    except Exception:
        emit("notice", NOTICE_RULES)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
