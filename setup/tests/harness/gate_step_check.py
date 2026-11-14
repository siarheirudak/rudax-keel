#!/usr/bin/env python3
"""Run the real keel-gate Gate step from checks.yml on a scratch repo.

The step's run: block is read from .github/workflows/checks.yml at test
time, so the test follows the live workflow. Each case builds a base commit
from this tree's verdict chain, a pull request branch, and a --no-ff merge
commit (like refs/pull/N/merge), then runs the block with a clean runner
environment. No network: GITHUB_TOKEN is empty, so a diff that needs
mutants stays red with "mutants: token missing".

The run: block alone cannot see the step's env:, if:, continue-on-error,
shell: or the job's checkout. Cases G-Y1..G-Y7 check that YAML text, so a
workflow edit that moots the base pin there is red too (Auditor F1, FU-A).
They are text checks of one job and the top-level keys, not a YAML parser:
some harmless styles fail too (see the P1b brief), which is fail-safe.

Prints one RESULT line per case. BLOCKED means the case held.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "checks.yml")
JOBS = os.path.join(ROOT, "scripts", "gate-jobs.txt")
GATE = os.path.join(ROOT, "scripts", "check-gate.sh")
MARKER = "verdict chain from"


def gate_run_block(text):
    """Return the run: block of the Gate step in the keel-gate job, or None."""
    lines = text.splitlines()
    job = None
    for index, line in enumerate(lines):
        if re.match(r"^  keel-gate:\s*$", line):
            job = index
            break
    if job is None:
        return None
    end = len(lines)
    for index in range(job + 1, len(lines)):
        if re.match(r"^  \S", lines[index]):
            end = index
            break
    step = None
    for index in range(job + 1, end):
        if re.match(r"^\s*- name: Gate\s*$", lines[index]):
            step = index
            break
    if step is None:
        return None
    step_indent = len(lines[step]) - len(lines[step].lstrip())
    for index in range(step + 1, end):
        line = lines[index]
        indent = len(line) - len(line.lstrip())
        if line.strip() and indent <= step_indent:
            return None
        match = re.match(r"^(\s*)run: \|\s*$", line)
        if not match:
            continue
        key_indent = len(match.group(1))
        body = []
        for inner in lines[index + 1:end]:
            if inner.strip() and len(inner) - len(inner.lstrip()) <= key_indent:
                break
            body.append(inner)
        while body and not body[-1].strip():
            body.pop()
        firsts = [len(b) - len(b.lstrip()) for b in body if b.strip()]
        if not firsts:
            return None
        cut = min(firsts)
        return "\n".join(b[cut:] if b.strip() else "" for b in body) + "\n"
    return None


PIN = "${{ github.event.pull_request.base.sha }}"
# The Gate step env is exactly these keys plus one R_<JOB> per needs job, each
# once, with exactly these values. Any other key (BASH_ENV, PATH, GIT_DIR,
# GITHUB_WORKSPACE, ...) can change what the run: block runs.
STEP_ENV = {
    "GITHUB_EVENT_NAME": "${{ github.event_name }}",
    "GITHUB_REPOSITORY": "${{ github.repository }}",
    "GITHUB_BASE_REF": "${{ github.base_ref }}",
    "KEEL_MUTATE_BASE": PIN,
    "GITHUB_TOKEN": "${{ github.token }}",
    "DEFAULT_BRANCH": "${{ github.event.repository.default_branch }}",
    "GATE_PR_BASE_SHA": PIN,
}
STEP_KEYS = ["name", "env", "run"]
JOB_KEYS = ["name", "needs", "if", "runs-on", "timeout-minutes", "permissions", "steps"]
JOB_TIMEOUT = "5"
TOP_KEYS = ("name", "on", "permissions", "concurrency", "jobs")
CHECKOUT = "actions/checkout@"
PLAIN_KEY = re.compile(r"^(- )?[A-Za-z0-9_-]+:(\s|$)")


def _indent(line):
    return len(line) - len(line.lstrip())


def _keys(lines, indent):
    """Mapping keys at exactly this indent, in order."""
    found = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lead = _indent(line) + (2 if stripped.startswith("- ") else 0)
        if lead != indent:
            continue
        match = re.match(r"^ *(- )?([A-Za-z0-9_-]+):(\s|$)", line)
        if match:
            found.append((match.group(2), line.split(":", 1)[1].strip()))
        else:
            # A quoted key, a merge key or a flow mapping: not a plain key.
            found.append(("?" + stripped, ""))
    return found


def gate_job(text):
    """(top-level keys, job lines, steps) of the keel-gate job, or None.

    steps is a list of line lists, one per "- " item under steps:.
    """
    lines = text.splitlines()
    top = [m.group(1) for m in (re.match(r"^([A-Za-z0-9_-]+):", l) for l in lines) if m]
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^  keel-gate:\s*$", line):
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^  \S", lines[index]) or re.match(r"^\S", lines[index]):
            end = index
            break
    body = lines[start + 1:end]
    steps = []
    in_steps = False
    for line in body:
        if re.match(r"^    steps:\s*$", line):
            in_steps = True
            continue
        if in_steps and line.strip() and _indent(line) <= 4:
            in_steps = False
        if not in_steps:
            continue
        if re.match(r"^      - ", line):
            steps.append([line])
        elif steps:
            steps[-1].append(line)
    return top, body, steps


def top_errors(text):
    """Top-level lines must be plain keys from TOP_KEYS, each once."""
    problems = []
    seen = []
    for line in text.splitlines():
        if not line.strip() or line.startswith((" ", "#")):
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):(\s|$)", line)
        if not match:
            problems.append("top-level line is not a plain key: %r" % line.strip())
            continue
        seen.append(match.group(1))
    extra = [key for key in seen if key not in TOP_KEYS]
    if extra:
        problems.append("workflow top-level keys %s are not allowed (only %s; no env: or defaults:)" % (extra, ", ".join(TOP_KEYS)))
    dups = sorted({key for key in seen if seen.count(key) > 1})
    if dups:
        problems.append("workflow top-level keys repeated: %s" % dups)
    return problems


def plain_errors(body):
    """Every key line in the job is a plain key, no flow mapping, merge key,
    anchor, alias or tag, and no key repeats inside one mapping."""
    problems = []
    stack = []  # (indent, keys) for open mappings
    block = None  # indent of a run: | key whose body is being skipped
    for line in body:
        stripped = line.strip()
        if not stripped:
            continue
        indent = _indent(line)
        if block is not None:
            if indent > block:
                continue
            block = None
        if stripped.startswith("#"):
            continue
        if not PLAIN_KEY.match(stripped):
            problems.append("not a plain key: %r" % stripped)
            continue
        item = stripped.startswith("- ")
        key = stripped[2:].split(":", 1)[0] if item else stripped.split(":", 1)[0]
        value = stripped.split(":", 1)[1].strip()
        at = indent + 2 if item else indent
        while stack and (stack[-1][0] > at or (item and stack[-1][0] >= at)):
            stack.pop()
        if stack and stack[-1][0] == at:
            if key in stack[-1][1]:
                problems.append("repeated key %r" % key)
            stack[-1][1].add(key)
        else:
            stack.append((at, {key}))
        if value[:1] in ("{", "&", "*", "!") or value.startswith("<<"):
            problems.append("value of %r is a flow mapping, anchor, alias or tag" % key)
        if value in ("|", "|-", "|+", ">", ">-", ">+"):
            block = at
    return problems


def yaml_errors(text):
    """Return {case: [problems]} for the keel-gate job and Gate step YAML."""
    errors = {name: [] for name in ("G-Y1", "G-Y2", "G-Y3", "G-Y4", "G-Y5", "G-Y6", "G-Y7")}
    errors["G-Y5"].extend(top_errors(text))
    parsed = gate_job(text)
    if parsed is None:
        for name in errors:
            errors[name].append("keel-gate job not found")
        return errors
    top, body, steps = parsed
    errors["G-Y6"].extend(plain_errors(body))
    job_keys = _keys(body, 4)
    names = [key for key, _ in job_keys]
    if sorted(names) != sorted(JOB_KEYS):
        errors["G-Y3"].append("keel-gate job keys are %s, expected %s" % (names, JOB_KEYS))
    if dict(job_keys).get("if") != "always()":
        errors["G-Y3"].append("keel-gate job must have if: always()")
    if dict(job_keys).get("timeout-minutes") != JOB_TIMEOUT:
        errors["G-Y3"].append("keel-gate job must have timeout-minutes: %s" % JOB_TIMEOUT)
    needs = re.match(r"^\[([^\]]*)\]$", dict(job_keys).get("needs", ""))
    needed = [part.strip() for part in needs.group(1).split(",") if part.strip()] if needs else []
    if not needed:
        errors["G-Y1"].append("keel-gate needs list not found")
    gates = [step for step in steps if re.match(r"^      - name: Gate\s*$", step[0])]
    if len(steps) != 2 or len(gates) != 1 or steps[1] is not gates[0]:
        errors["G-Y4"].append("keel-gate steps must be exactly checkout, then Gate")
        if not gates:
            errors["G-Y1"].append("Gate step not found")
            errors["G-Y2"].append("Gate step not found")
            return errors
    gate = gates[0]
    step_keys = [key for key, _ in _keys(gate, 8)]
    if step_keys != STEP_KEYS:
        errors["G-Y2"].append("Gate step keys are %s, expected %s (no if:, shell:, continue-on-error)" % (step_keys, STEP_KEYS))
    env = []
    in_env = False
    for line in gate[1:]:
        if re.match(r"^        env:\s*$", line):
            in_env = True
            continue
        if in_env and line.strip() and _indent(line) <= 8:
            in_env = False
        if in_env:
            env.append(line)
    pairs = _keys(env, 10)
    allowed = dict(STEP_ENV)
    for job in needed:
        allowed[env_name(job)] = "${{ needs.%s.result }}" % job
    names = [name for name, _ in pairs]
    extra = [name for name in names if name not in allowed]
    if extra:
        errors["G-Y1"].append("Gate env has keys that are not allowed: %s" % extra)
    for key, want in STEP_ENV.items():
        got = [value for name, value in pairs if name == key]
        if got != [want]:
            errors["G-Y1"].append("Gate env %s is %s, expected exactly [%s]" % (key, got, want))
    for name, value in pairs:
        if name.startswith("R_") and name in allowed and value != allowed[name]:
            errors["G-Y1"].append("Gate env %s is %r, expected %r" % (name, value, allowed[name]))
    dups = sorted({name for name in names if names.count(name) > 1})
    if dups:
        errors["G-Y1"].append("Gate env repeats %s" % dups)
    block = gate_run_block(text) or ""
    if "${{" in block:
        errors["G-Y7"].append("the Gate run: block uses ${{ }}; pass values through env: instead")
    checkout = steps[0] if steps else []
    if not checkout or not any(CHECKOUT in line for line in checkout[:1]):
        errors["G-Y4"].append("first keel-gate step is not actions/checkout")
    else:
        with_keys = dict(_keys(checkout, 10))
        if with_keys.get("fetch-depth") != "0":
            errors["G-Y4"].append("checkout must use fetch-depth: 0")
        if with_keys.get("persist-credentials") != "false":
            errors["G-Y4"].append("checkout must use persist-credentials: false")
        extra = [key for key, _ in _keys(checkout, 8) if key not in ("uses", "with")]
        if extra:
            errors["G-Y4"].append("checkout step has extra keys %s" % extra)
    return errors


def job_names():
    names = []
    with open(JOBS, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#"):
                names.append(line)
    return names


def env_name(job):
    return "R_" + job.upper().replace("-", "_")


class Scratch:
    def __init__(self, root):
        self.root = root
        self.repo = os.path.join(root, "repo")
        self.home = os.path.join(root, "home")
        os.makedirs(self.repo)
        os.makedirs(self.home)
        self.genv = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": self.home,
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        }

    def git(self, *args):
        proc = subprocess.run(
            ["git", "-C", self.repo, "-c", "core.hooksPath=/dev/null", *args],
            env=self.genv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError("git %s: %s" % (" ".join(args), proc.stderr.strip()))
        return proc.stdout.strip()

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def remove(self, rel):
        os.remove(os.path.join(self.repo, rel))

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")


def copy_chain(dest):
    """This tree's verdict chain, as a base commit would hold it."""
    os.makedirs(os.path.join(dest, "scripts"), exist_ok=True)
    shutil.copy2(GATE, os.path.join(dest, "scripts", "check-gate.sh"))
    shutil.copy2(JOBS, os.path.join(dest, "scripts", "gate-jobs.txt"))
    target = os.path.join(dest, "setup", "tests", "harness")
    shutil.copytree(
        HERE,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "logs", "*.pyc"),
    )


def build(root, base_edit=None, pr_edit=None):
    """Return (scratch, base_sha, merge_sha)."""
    s = Scratch(root)
    s.git("init", "-q", "-b", "main")
    copy_chain(s.repo)
    s.write("docs/a.md", "a\n")
    if base_edit:
        base_edit(s)
    base = s.commit("base")
    s.git("checkout", "-q", "-b", "pr")
    if pr_edit:
        pr_edit(s)
    s.commit("pr")
    s.git("checkout", "-q", "--detach", base)
    s.git("merge", "-q", "--no-ff", "--no-edit", "pr")
    merge = s.git("rev-parse", "HEAD")
    return s, base, merge


def run_step(block, s, event, sha, base, extra=None, drop=()):
    script = os.path.join(s.root, "step.sh")
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(block)
    runner_temp = os.path.join(s.root, "runner-temp")
    os.makedirs(runner_temp, exist_ok=True)
    env = dict(s.genv)
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "RUNNER_TEMP": runner_temp,
        "GITHUB_WORKSPACE": s.repo,
        "GITHUB_EVENT_NAME": event,
        "GITHUB_SHA": sha,
        "GITHUB_REF": "refs/pull/7/merge" if event == "pull_request" else "refs/heads/main",
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_BASE_REF": "main" if event == "pull_request" else "",
        "GITHUB_TOKEN": "",
        "DEFAULT_BRANCH": "main",
        "GATE_PR_BASE_SHA": base if event == "pull_request" else "",
        "KEEL_MUTATE_BASE": base if event == "pull_request" else "",
    })
    for job in job_names():
        env[env_name(job)] = "success"
    env.update(extra or {})
    for name in drop:
        env.pop(name, None)
    proc = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", script],
        cwd=s.repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300,
    )
    return proc.returncode, proc.stdout


TAMPER_GATE = "#!/usr/bin/env bash\necho TAMPERED-GATE\nexit 0\n"
TAMPER_RESULT = "import sys\nprint('TAMPERED-RESULT')\nsys.exit(0)\n"
DECOY = "print('DECOY-IMPORT')\nraise SystemExit(0)\n"


def tamper(s):
    s.write("scripts/check-gate.sh", TAMPER_GATE)
    s.write("setup/tests/harness/mutant-result.py", TAMPER_RESULT)
    s.write("setup/tests/harness/json.py", DECOY)


def main():
    results = []

    def res(name, ok, detail):
        results.append(ok)
        print("RESULT %s: %s (%s)" % (name, "BLOCKED" if ok else "NOT BLOCKED", detail))

    try:
        text = open(WORKFLOW, encoding="utf-8").read()
    except OSError:
        res("G-X0", False, "checks.yml missing")
        return 1
    block = gate_run_block(text)
    if not block or MARKER not in block or "set -euo pipefail" not in block:
        res("G-X0", False, "Gate run block not found in checks.yml")
        return 1
    res("G-X0", True, "Gate run block read from checks.yml")

    labels = {
        "G-Y1": "Gate env is the exact key set with pinned values",
        "G-Y2": "Gate step has only name, env, run",
        "G-Y3": "keel-gate job runs if: always(), timeout-minutes: 5, no extra keys",
        "G-Y4": "steps are checkout (fetch-depth 0, no credentials) then Gate",
        "G-Y5": "workflow top-level keys are only name, on, permissions, concurrency, jobs",
        "G-Y6": "keel-gate job has only plain, unrepeated keys",
        "G-Y7": "Gate run: block has no ${{ }} expressions",
    }
    for name, problems in yaml_errors(text).items():
        res(name, not problems, labels[name] + (": " + "; ".join(problems) if problems else ""))

    root = tempfile.mkdtemp(prefix="gate-step-")
    try:
        def case(tag):
            path = os.path.join(root, tag)
            return path

        # Honest pull request: a docs edit. Green, base chain, no mutants needed.
        s, base, merge = build(case("h1"), pr_edit=lambda s: s.write("docs/a.md", "b\n"))
        code, out = run_step(block, s, "pull_request", merge, base)
        res("G-H1", code == 0 and (MARKER + " " + base) in out and "mutants: not required" in out,
            "honest pull request is green from base %s (exit %s)" % (base[:7], code))

        # Push to main: the chain comes from GITHUB_SHA.
        s, base, merge = build(case("h2"))
        code, out = run_step(block, s, "push", merge, "")
        res("G-H2", code == 0 and (MARKER + " " + merge) in out,
            "push uses GITHUB_SHA (exit %s)" % code)

        # Tampered chain and a decoy import on the pull request: the base chain still decides.
        s, base, merge = build(case("a1"), pr_edit=tamper)
        code, out = run_step(block, s, "pull_request", merge, base)
        leaked = any(word in out for word in ("TAMPERED-GATE", "TAMPERED-RESULT", "DECOY-IMPORT"))
        res("G-A1", code != 0 and not leaked and (MARKER + " " + base) in out and "not success: mutants" in out,
            "tampered check-gate.sh, mutant-result.py, decoy json.py stay red (exit %s)" % code)

        # The pull request drops a job from gate-jobs.txt; base still lists it.
        first = job_names()[0]

        def drop_job(s):
            kept = [name for name in job_names() if name != first]
            s.write("scripts/gate-jobs.txt", "\n".join(kept) + "\n")

        s, base, merge = build(case("a2"), pr_edit=drop_job)
        code, out = run_step(block, s, "pull_request", merge, base, drop=(env_name(first),))
        res("G-A2", code != 0 and ("not success: " + first) in out,
            "gate-jobs.txt from base keeps %s required (exit %s)" % (first, code))

        # Bad base values.
        s, base, merge = build(case("a6"), pr_edit=lambda s: s.write("docs/a.md", "b\n"))
        bad = []
        for label, value in (("empty", ""), ("short", base[:39]), ("upper", base.upper())):
            code, out = run_step(block, s, "pull_request", merge, value)
            if code == 0 or "missing or not a full SHA" not in out:
                bad.append(label)
        res("G-A6", not bad, "empty, 39-hex and uppercase base are refused%s" % (": " + ",".join(bad) if bad else ""))

        # Unknown events.
        bad = []
        for event in ("workflow_dispatch", "pull_request_target", "merge_group"):
            code, out = run_step(block, s, event, merge, base,
                                 extra={"GATE_PR_BASE_SHA": base, "KEEL_MUTATE_BASE": base})
            if code == 0 or "runs only on pull_request and push" not in out:
                bad.append(event)
        res("G-A7", not bad, "unknown events are refused%s" % (": " + ",".join(bad) if bad else ""))

        # Base lacks mutant-result.py: red on pull_request and on push, with the named-file message.
        s, base, merge = build(case("a8"), base_edit=lambda s: s.remove("setup/tests/harness/mutant-result.py"),
                               pr_edit=lambda s: s.write("docs/a.md", "b\n"))
        bad = []
        for event, sha, b in (("pull_request", merge, base), ("push", base, "")):
            code, out = run_step(block, s, event, sha, b)
            if code == 0 or "mutant-result.py is missing at base" not in out:
                bad.append(event)
        res("G-A8", not bad, "a missing entry file at base is red%s" % (": " + ",".join(bad) if bad else ""))

        # A well-formed base that is not in the checkout.
        code, out = run_step(block, s, "pull_request", merge, "0" * 40)
        res("G-A9", code != 0 and "is not in the checkout" in out,
            "absent base commit is red (exit %s)" % code)
    except Exception as err:  # a broken scratch setup is a failure, not a pass
        res("G-X1", False, "scratch setup failed: %s" % err)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
