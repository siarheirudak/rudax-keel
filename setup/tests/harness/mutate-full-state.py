#!/usr/bin/env python3
"""Full-run freshness and red state. Read from the API by main's code."""
import json
import os
import sys
import urllib.request

FULL_WORKFLOW = ".github/workflows/mutate-full.yml"
WEEKLY_CRON = "17 18 * * 1"
COUNTED_EVENTS = frozenset({"schedule", "workflow_dispatch"})

skip_noise = True  # skip-noise
filter_runs = True  # filter-runs
fail_open = True  # fresh-api-run
trust_state = True  # trust-state


def run_filters_ok(run, default_branch):
    if not filter_runs:
        return True
    if run.get("path") not in (None, FULL_WORKFLOW) and run.get("path") != FULL_WORKFLOW:
        return False
    path = run.get("path") or FULL_WORKFLOW
    if path != FULL_WORKFLOW:
        return False
    if run.get("event") not in COUNTED_EVENTS:
        return False
    if run.get("head_branch") != default_branch:
        return False
    return True


def is_real_green(run, state, default_branch):
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        return False
    if not run_filters_ok(run, default_branch):
        return False
    if not trust_state:
        return run.get("job_name") != "skip"
    if not state or state.get("missing") or state.get("expired"):
        return False
    if state.get("mode") != "run" or not state.get("full_plan"):
        return False
    return True


def is_fresh_skip(run, state):
    if not state:
        return False
    return state.get("mode") == "skip"


def latest_counted(runs, states, default_branch):
    """Newest completed full run that is not a cancellation or a freshness skip."""
    for run in runs:
        if not run_filters_ok(run, default_branch):
            continue
        if run.get("status") != "completed":
            continue
        state = states.get(run.get("id"))
        if skip_noise and run.get("conclusion") in ("cancelled", "skipped"):
            continue
        if skip_noise and is_fresh_skip(run, state):
            continue
        return run, state
    return None, None


def is_red(runs, states, default_branch):
    run, _state = latest_counted(runs, states, default_branch)
    if run is None:
        return False
    return run.get("conclusion") in ("failure", "timed_out")


def fresh_decision(event, schedule, main_sha, green_sha, api_error):
    if event == "workflow_dispatch" or schedule == WEEKLY_CRON:
        return "run"
    if api_error:
        return "run" if fail_open else "skip"
    if green_sha and main_sha == green_sha:
        return "skip"
    return "run"


def meaningful_full_runs(runs, states, default_branch):
    counted = []
    for run in runs:
        if not run_filters_ok(run, default_branch):
            continue
        if run.get("status") != "completed":
            continue
        if run.get("conclusion") in ("cancelled", "skipped"):
            continue
        state = states.get(run.get("id"))
        if state and state.get("mode") == "skip":
            continue
        counted.append(run)
    return counted


def saw_green_all(runs, states, default_branch):
    for run in runs:
        state = states.get(run.get("id"))
        if is_real_green(run, state, default_branch) and state and state.get("green_all"):
            return True
    return False


def bootstrap_overdue(runs, states, default_branch, limit):
    if saw_green_all(runs, states, default_branch):
        return False
    return len(meaningful_full_runs(runs, states, default_branch)) >= limit


def blocking_ids(failures, red_counts, ci, offline):
    mode = red_counts
    if mode == "all":
        return list(failures)
    if mode == "ci+offline":
        live = set(ci) | set(offline)
        return [mid for mid in failures if mid in live]
    raise ValueError("red counts")


def run_should_fail(failures, red_counts, ci, offline, overdue):
    """A bootstrap notice on its own does not fail the run."""
    return bool(blocking_ids(failures, red_counts, ci, offline))


def notice_needed(state):
    return bool(state and state.get("bootstrap_overdue"))


def latest_green_sha(runs, states, default_branch):
    for run in runs:
        state = states.get(run.get("id"))
        if is_real_green(run, state, default_branch):
            return run.get("head_sha")
    return None


def _api_json(url, token):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "rudax-keel-mutants",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_runs(repo, token, limit_pages=2):
    runs = []
    for page in range(1, limit_pages + 1):
        url = (
            "https://api.github.com/repos/%s/actions/workflows/mutate-full.yml/runs"
            "?per_page=50&page=%d" % (repo, page)
        )
        payload = _api_json(url, token)
        batch = payload.get("workflow_runs") if isinstance(payload, dict) else None
        if not isinstance(batch, list):
            raise RuntimeError("runs")
        runs.extend(batch)
        if len(batch) < 50:
            break
    return runs


def fetch_one_state(repo, token, run_id):
    import io
    import zipfile
    listed = _api_json(
        "https://api.github.com/repos/%s/actions/runs/%s/artifacts?per_page=100" % (repo, run_id),
        token,
    )
    artifacts = listed.get("artifacts") if isinstance(listed, dict) else None
    if not isinstance(artifacts, list):
        return {"missing": True}
    chosen = None
    for item in artifacts:
        if item.get("name") == "state" and not item.get("expired"):
            chosen = item
            break
    if chosen is None:
        return {"missing": True}
    url = chosen.get("archive_download_url") or ""
    if not url:
        return {"missing": True}
    import mutate_shards
    blob = mutate_shards.github_bytes(url, token)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        name = next((info.filename for info in archive.infolist() if info.filename.endswith("state.json")), None)
        if name is None:
            return {"missing": True}
        return json.loads(archive.read(name).decode("utf-8"))


def state_map(repo, token, runs):
    states = {}
    checked = 0
    for run in runs:
        if checked >= 8:
            break
        if run.get("conclusion") != "success" or run.get("status") != "completed":
            continue
        checked += 1
        try:
            states[run.get("id")] = fetch_one_state(repo, token, run.get("id"))
        except Exception:
            states[run.get("id")] = {"missing": True}
    return states


def normalize_run(item):
    return {
        "id": item.get("id"),
        "path": item.get("path") or FULL_WORKFLOW,
        "event": item.get("event"),
        "status": item.get("status"),
        "conclusion": item.get("conclusion"),
        "head_branch": item.get("head_branch"),
        "head_sha": item.get("head_sha"),
        "job_name": item.get("name") or "",
    }


def write_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        print("%s=%s" % (name, value))
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("%s=%s\n" % (name, value))


def decide_from_env():
    event = os.environ.get("GITHUB_EVENT_NAME") or ""
    schedule = os.environ.get("GITHUB_EVENT_SCHEDULE") or ""
    main_sha = os.environ.get("MAIN_SHA") or ""
    default_branch = os.environ.get("DEFAULT_BRANCH") or "main"
    repo = os.environ.get("REPO") or ""
    token = os.environ.get("GH_TOKEN") or ""
    api_error = False
    runs = []
    try:
        if token and repo:
            runs = [normalize_run(item) for item in fetch_runs(repo, token)]
        else:
            api_error = True
    except Exception:
        api_error = True
        runs = []
    states = {}
    if not api_error:
        try:
            states = state_map(repo, token, runs)
        except Exception:
            api_error = True
            states = {}
    green = None if api_error else latest_green_sha(runs, states, default_branch)
    raw_state = os.environ.get("STATE_JSON") or ""
    if raw_state and not api_error:
        try:
            supplied = json.loads(raw_state)
        except json.JSONDecodeError:
            supplied = {}
        if isinstance(supplied, dict):
            states = supplied
            green = latest_green_sha(runs, states, default_branch)
    mode = fresh_decision(event, schedule, main_sha, green, api_error)
    write_output("mode", mode)
    return 0


def self_test():
    branch = "main"
    failure = {
        "id": 1,
        "path": FULL_WORKFLOW,
        "event": "schedule",
        "status": "completed",
        "conclusion": "failure",
        "head_branch": branch,
        "head_sha": "a" * 40,
    }
    cancelled = dict(failure, id=2, conclusion="cancelled", head_sha="b" * 40)
    skip_run = dict(failure, id=3, conclusion="success", head_sha="c" * 40)
    push = dict(failure, id=4, event="push", conclusion="success", head_sha="d" * 40)
    green = dict(failure, id=5, conclusion="success", head_sha="e" * 40)
    states = {
        3: {"mode": "skip"},
        5: {"mode": "run", "full_plan": True, "green_all": True},
    }
    if not is_red([cancelled, failure], states, branch):
        return "cancelled did not keep red"
    if not is_red([skip_run, failure], states, branch):
        return "skip did not keep red"
    if is_red([push, failure], states, branch) is False and filter_runs:
        pass
    if not is_red([push, failure], {**states}, branch):
        return "other event cleared red"
    if is_real_green(green, None, branch):
        return "missing state counted as green"
    if is_real_green(green, {"expired": True, "mode": "run", "full_plan": True}, branch):
        return "expired state counted as green"
    named = dict(green, job_name="mutants")
    if is_real_green(named, None, branch):
        return "missing state counted as green"
    if is_real_green(named, {"mode": "skip"}, branch):
        return "skip state counted as green"
    if is_real_green(green, states[5], branch) is not True:
        return "real green missed"
    if fresh_decision("schedule", "17 18 * * *", "abc", "abc", False) != "skip":
        return "unchanged main did not skip"
    if fresh_decision("schedule", "17 18 * * *", "abc", "def", False) != "run":
        return "moved main did not run"
    if fresh_decision("schedule", WEEKLY_CRON, "abc", "abc", False) != "run":
        return "weekly did not run"
    if fresh_decision("schedule", "17 18 * * *", "abc", "abc", True) != "run":
        return "api error skipped"
    if fresh_decision("workflow_dispatch", "", "abc", "abc", False) != "run":
        return "dispatch skipped"
    if run_should_fail(["M02"], "ci+offline", ["M03"], ["M01"], True):
        return "bootstrap or full-only failed the run"
    if not run_should_fail(["M02"], "all", ["M03"], ["M01"], False):
        return "all-mode failure did not fail"
    if not bootstrap_overdue([failure] * 7, {}, branch, 7):
        return "bootstrap limit missed"
    if bootstrap_overdue([green], states, branch, 7):
        return "green all stayed overdue"
    return ""


def main(argv):
    if argv[1:2] == ["--self-test"]:
        err = self_test()
        if err:
            print(err, file=sys.stderr)
            return 1
        print("mutate full state: self-test holds")
        return 0
    if argv[1:2] == ["fresh"]:
        return decide_from_env()
    print("usage: mutate-full-state.py --self-test | fresh", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
