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
        if re.match(r"^  \S", lines[index]) and not _comment(lines[index]):
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
        if line.strip() and indent <= step_indent and not _comment(line):
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
# The checkout step must be the official action, once, at a full SHA, and every
# other checkout in the workflow must use that same value.
checkout_owner = True  # checkout-owner
checkout_same_pin = True  # checkout-same-pin
checkout_full_sha = True  # checkout-full-sha
CHECKOUT_WITH = ("fetch-depth", "persist-credentials")
# Fixed other SHA for the synthetic pin cases. The live SHA is read from the file.
_OTHER_SHA = "a2b4c680a2b4c680a2b4c680a2b4c680a2b4c680"
_OTHER_SHA_ALT = "b4c680a2b4c680a2b4c680a2b4c680a2b4c680a2"
# Needle used only while deriving the synthetic cases. The live scan stays literal.
_MATRIX_NEEDLE = "actions/checkout"
PLAIN_KEY = re.compile(r"^(- )?[A-Za-z0-9_-]+:(\s|$)")


def _comment(line):
    """A comment-only line. YAML ignores it, so it ends no job, step or map
    (Security F-01). Inside a run: | body it is script text and is kept there."""
    return line.lstrip().startswith("#")


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
        line = lines[index]
        if (re.match(r"^  \S", line) or re.match(r"^\S", line)) and not _comment(line):
            end = index
            break
    # Comment-only lines carry no keys. Dropping them keeps a comment from
    # ending the steps or env scan early (Security F-01).
    body = [line for line in lines[start + 1:end] if not _comment(line)]
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


def _other_sha(live):
    """A full SHA other than the ref read from the workflow."""
    if live != _OTHER_SHA:
        return _OTHER_SHA
    return _OTHER_SHA_ALT


def _run_limit(line):
    """Indent of a run: block body, 'inline' for a one-line script, else None."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    indent = _indent(line)
    item = stripped.startswith("- ")
    body = stripped[2:].lstrip() if item else stripped
    match = re.match(r"run:\s*(.*)$", body)
    if not match:
        return None
    value = match.group(1).strip()
    logical = indent + 2 if item else indent
    if value.startswith("|") or value.startswith(">"):
        return logical
    if value and not value.startswith("#"):
        return "inline"
    return None


def _code_lines(text):
    """Lines that are not comments and not inside a run: script body."""
    lines = text.splitlines()
    run_limit = None
    job = ""
    rows = []
    for index, line in enumerate(lines):
        if run_limit is not None:
            if line.strip() and _indent(line) <= run_limit:
                run_limit = None
            else:
                continue
        if _comment(line):
            continue
        if re.match(r"^  [A-Za-z0-9_-]+:\s*(?:#.*)?$", line):
            job = line.strip().split(":", 1)[0]
        limit = _run_limit(line)
        if limit == "inline":
            continue
        if isinstance(limit, int):
            run_limit = limit
            continue
        rows.append((index, line, job))
    return rows


def _keel_span(lines):
    """Line range of the keel-gate job, or None."""
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^  keel-gate:\s*(?:#.*)?$", line):
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip() or _comment(line):
            continue
        if _indent(line) <= 2:
            end = index
            break
    return start, end


def _quoted_uses_backslash(line):
    """True when a uses: value is double-quoted and contains a backslash."""
    idx = 0
    while idx < len(line):
        match = re.search(r"(?:^|[\s{,])uses\s*:\s*\"", line[idx:])
        if not match:
            return False
        pos = idx + match.end()
        while pos < len(line):
            if line[pos] == "\\":
                return True
            if line[pos] == "\"":
                break
            pos += 1
        idx = pos + 1
    return False


def _parse_double(rest):
    chars = []
    pos = 1
    while pos < len(rest):
        if rest[pos] == "\"":
            return "".join(chars), True
        chars.append(rest[pos])
        pos += 1
    return None, False


def _parse_single(rest):
    chars = []
    pos = 1
    while pos < len(rest):
        if rest[pos] == "'":
            if pos + 1 < len(rest) and rest[pos + 1] == "'":
                chars.append("'")
                pos += 2
                continue
            return "".join(chars), True
        chars.append(rest[pos])
        pos += 1
    return None, False


def _uses_value(line):
    """(value, kind) of the first uses: scalar on the line.

    kind is plain, quoted, unreadable, or missing.
    """
    match = re.search(r"(?:^|[\s{,])uses\s*:\s*", line)
    if not match:
        return None, "missing"
    rest = line[match.end():]
    if rest.startswith("\""):
        if _quoted_uses_backslash(line):
            return None, "unreadable"
        value, ok = _parse_double(rest)
        if not ok:
            return None, "unreadable"
        return value, "quoted"
    if rest.startswith("'"):
        value, ok = _parse_single(rest)
        if not ok:
            return None, "unreadable"
        return value, "quoted"
    if rest.startswith("|") or rest.startswith(">"):
        return None, "unreadable"
    token = re.match(r"([^#\s,}]+)", rest)
    if not token:
        return None, "unreadable"
    return token.group(1), "plain"


def _split_action(value):
    """(owner/repo, subpath, ref) or None."""
    if "@" not in value:
        return None
    path, ref = value.split("@", 1)
    parts = path.split("/")
    if len(parts) < 2 or parts[0] == "" or parts[1] == "":
        return None
    return parts[0] + "/" + parts[1], "/".join(parts[2:]), ref


def _scan_uses(text, needle="actions/checkout"):
    """Checkout reference lines and double-quoted uses lines that contain a backslash."""
    lines = text.splitlines()
    span = _keel_span(lines)
    folded = needle.casefold()
    refs = []
    escapes = []
    for index, line, job in _code_lines(text):
        keel = bool(span) and span[0] <= index < span[1]
        if _quoted_uses_backslash(line):
            escapes.append((job or "workflow", keel))
        if folded not in line.casefold():
            continue
        value, kind = _uses_value(line)
        refs.append({
            "index": index,
            "job": job or "workflow",
            "keel": keel,
            "value": value,
            "kind": kind,
        })
    return refs, escapes


def checkout_file_problems(text, needle="actions/checkout"):
    """G-Y4 problems from checkout reference lines and unreadable uses values."""
    problems = []
    refs, escapes = _scan_uses(text, needle)
    for job, _keel in escapes:
        problems.append("%s unreadable uses value" % job)
    if not refs:
        problems.append("no checkout reference line")
        return problems
    keel_value = None
    outside = 0
    for ref in refs:
        readable = ref["kind"] in ("plain", "quoted") and ref["value"] is not None
        if not readable:
            problems.append("%s unreadable checkout reference" % ref["job"])
        if ref["keel"] and keel_value is None and readable:
            keel_value = ref["value"]
        if not ref["keel"]:
            outside += 1
    if outside == 0:
        problems.append("keel-gate non-empty rule: no checkout reference outside keel-gate")
    if keel_value is None:
        return problems
    parsed = _split_action(keel_value)
    if checkout_owner:
        if not parsed or parsed[0] != "actions/checkout" or parsed[1] != "":
            problems.append(
                "keel-gate owner rule: owner/repo is not actions/checkout with an empty subpath"
            )
    if checkout_full_sha:
        ref = parsed[2] if parsed else ""
        if not re.fullmatch(r"[0-9a-f]{40}", ref or ""):
            problems.append("keel-gate full-SHA rule: ref is not 40 lower-case hex")
    if checkout_same_pin:
        for ref in refs:
            if ref["keel"] or ref["value"] is None:
                continue
            if ref["value"] != keel_value:
                problems.append(
                    "%s same-pin rule: checkout value differs from keel-gate" % ref["job"]
                )
    return problems


def mutate_pr_checkout_problems(text):
    """Empty when every checkout line in the file is official and shares one SHA.

    The caller prints a missing-style line when the result is not empty.
    """
    refs, escapes = _scan_uses(text)
    if escapes:
        return "readable uses value"
    if not refs:
        return "checkout reference"
    shas = []
    for ref in refs:
        value = ref["value"]
        if ref["kind"] not in ("plain", "quoted") or value is None:
            return "readable uses value"
        if not re.fullmatch(r"actions/checkout@[0-9a-f]{40}", value):
            return "official checkout value"
        shas.append(value.split("@", 1)[1])
    if len(set(shas)) != 1:
        return "one shared checkout sha"
    return ""


def _join_lines(text, lines):
    body = "\n".join(lines)
    if text.endswith("\n"):
        body += "\n"
    return body


def _live_ref(text, needle):
    refs, _escapes = _scan_uses(text, needle)
    for ref in refs:
        if ref["keel"] and ref["value"]:
            parsed = _split_action(ref["value"])
            if parsed:
                return parsed[2]
    return ""


def _replace_values(text, new_value, needle, only_keel=False, only_outside=False, limit_outside=None):
    refs, _escapes = _scan_uses(text, needle)
    lines = text.splitlines()
    replaced = 0
    outside_done = 0
    for ref in refs:
        if not ref["value"]:
            continue
        if only_keel and not ref["keel"]:
            continue
        if only_outside and ref["keel"]:
            continue
        if limit_outside is not None and not ref["keel"]:
            if outside_done >= limit_outside:
                continue
        line = lines[ref["index"]]
        old = ref["value"]
        if line.count(old) != 1:
            continue
        lines[ref["index"]] = line.replace(old, new_value, 1)
        replaced += 1
        if not ref["keel"]:
            outside_done += 1
    return _join_lines(text, lines), replaced


def _drop_outside(text, needle):
    refs, _escapes = _scan_uses(text, needle)
    drop = {ref["index"] for ref in refs if not ref["keel"]}
    lines = [line for index, line in enumerate(text.splitlines()) if index not in drop]
    return _join_lines(text, lines), len(drop)


def _insert_second_uses(text, needle):
    refs, _escapes = _scan_uses(text, needle)
    keel = [ref for ref in refs if ref["keel"] and ref["value"]]
    if not keel:
        return text, 0
    ref = keel[0]
    lines = text.splitlines()
    lines.insert(ref["index"] + 1, "        uses: " + ref["value"])
    return _join_lines(text, lines), 1


def _flow_outside(text, other, needle):
    refs, _escapes = _scan_uses(text, needle)
    outside = [ref for ref in refs if not ref["keel"] and ref["value"]]
    if not outside:
        return text, 0
    ref = outside[0]
    lines = text.splitlines()
    lines[ref["index"]] = "      - {uses: Actions/Checkout@%s}" % other
    return _join_lines(text, lines), 1


def _block_outside(text, live, needle):
    refs, _escapes = _scan_uses(text, needle)
    outside = [ref for ref in refs if not ref["keel"]]
    if not outside:
        return text, 0
    ref = outside[0]
    lines = text.splitlines()
    lines[ref["index"]] = "      - uses: |"
    lines.insert(ref["index"] + 1, "          actions/checkout@" + live)
    return _join_lines(text, lines), 1


def _run_canary(text, token):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _comment(line):
            continue
        if not re.match(r"^\s*(?:- )?run:\s*\|", line):
            continue
        indent = "          "
        if index + 1 < len(lines) and lines[index + 1].strip():
            indent = re.match(r"^(\s*)", lines[index + 1]).group(1) or indent
        lines.insert(index + 1, indent + "echo actions/checkout@" + token)
        return _join_lines(text, lines), 1
    return text, 0


def _row(case_id, derived, replaced, expect, require_replace, touch_ok=True):
    problems = yaml_errors(derived).get("G-Y4", ["missing"])
    has = bool(problems)
    broken = (require_replace and replaced == 0) or not touch_ok
    return {
        "id": case_id,
        "replaced": replaced,
        "expect": expect,
        "has": has,
        "broken": broken,
        "ok": (not broken) and (has == expect),
        "problems": problems,
    }


def matrix_rows(text, needle=None):
    """Synthetic checkout cases derived from the live workflow text."""
    needle = _MATRIX_NEEDLE if needle is None else needle
    live = _live_ref(text, needle)
    other = _other_sha(live)
    short = live[:-1] if len(live) == 40 else ("a2b4c680" * 4 + "a2b4c68")
    upper = live.upper() if live else other.upper()
    rows = []
    rows.append(_row("S0", text, 0, False, False))
    derived, count = _replace_values(text, "actions/checkout@" + other, needle)
    rows.append(_row("S1", derived, count, False, True))
    derived, count = _replace_values(text, "evil/actions/checkout@" + live, needle)
    rows.append(_row("S2", derived, count, True, True))
    derived, count = _replace_values(text, "actions/checkout@" + other, needle, only_keel=True)
    rows.append(_row("S3", derived, count, True, True))
    tag, n_tag = _replace_values(text, "actions/checkout@v4", needle)
    hex39, n_39 = _replace_values(text, "actions/checkout@" + short, needle)
    up, n_up = _replace_values(text, "actions/checkout@" + upper, needle)
    p_tag = yaml_errors(tag).get("G-Y4", ["missing"])
    p_39 = yaml_errors(hex39).get("G-Y4", ["missing"])
    p_up = yaml_errors(up).get("G-Y4", ["missing"])
    s4_has = bool(p_tag) and bool(p_39) and bool(p_up)
    s4_broken = n_tag == 0 or n_39 == 0 or n_up == 0
    rows.append({
        "id": "S4",
        "replaced": n_tag,
        "expect": True,
        "has": s4_has,
        "broken": s4_broken,
        "ok": (not s4_broken) and s4_has,
        "problems": p_tag,
        "variants": {"v4": p_tag, "hex39": p_39, "upper": p_up},
    })
    derived, count = _replace_values(
        text, "actions/checkout@" + other, needle, only_outside=True, limit_outside=1
    )
    rows.append(_row("S5", derived, count, True, True))
    derived, count = _replace_values(text, "Actions/Checkout@" + live, needle, only_keel=True)
    rows.append(_row("S6", derived, count, True, True))
    derived, count = _drop_outside(text, needle)
    rows.append(_row("S7", derived, count, True, True))
    derived, count = _insert_second_uses(text, needle)
    rows.append(_row("S8", derived, count, True, True))
    derived, count = _replace_values(
        text, '"actions/checkout@%s"' % other, needle, only_outside=True, limit_outside=1
    )
    rows.append(_row("S9", derived, count, True, True))
    derived, count = _replace_values(text, '"actions/checkout@%s"' % live, needle, only_keel=True)
    rows.append(_row("S10", derived, count, True, True))
    derived, count = _flow_outside(text, other, needle)
    rows.append(_row("S11", derived, count, True, True))
    derived, count = _replace_values(
        text, "actions/checkout/subdir@" + live, needle, only_outside=True, limit_outside=1
    )
    rows.append(_row("S12", derived, count, True, True))
    derived, count = _block_outside(text, live, needle)
    rows.append(_row("S13", derived, count, True, True))
    derived, inserted = _run_canary(text, _OTHER_SHA_ALT)
    rows.append(_row("S14", derived, 0, False, False, touch_ok=inserted == 1))
    rows.append(_row("S15", "", 0, True, False))
    derived, count = _replace_values(
        text, '"ac\\tions/checkout@%s"' % live, needle, only_outside=True, limit_outside=1
    )
    rows.append(_row("S16", derived, count, True, True))
    return rows


def matrix_issues(text):
    """G-Y4 problems when a synthetic case misses its outcome or replaces nothing."""
    rows = matrix_rows(text)
    issues = []
    if not rows:
        issues.append("synthetic matrix ran zero cases")
        return issues
    for row in rows:
        if row["broken"]:
            issues.append("synthetic %s derivation replaced nothing" % row["id"])
        elif not row["ok"]:
            want = "a problem" if row["expect"] else "no problem"
            issues.append("synthetic %s: expected %s" % (row["id"], want))
    return issues


def yaml_errors(text):
    """Return {case: [problems]} for the keel-gate job and Gate step YAML."""
    errors = {name: [] for name in ("G-Y1", "G-Y2", "G-Y3", "G-Y4", "G-Y5", "G-Y6", "G-Y7")}
    errors["G-Y5"].extend(top_errors(text))
    parsed = gate_job(text)
    if parsed is None:
        for name in errors:
            errors[name].append("keel-gate job not found")
        errors["G-Y4"].extend(checkout_file_problems(text))
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
            errors["G-Y4"].extend(checkout_file_problems(text))
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
        uses = [value for key, value in _keys(checkout, 8) if key == "uses"]
        if len(uses) != 1:
            errors["G-Y4"].append("keel-gate checkout step must hold exactly one uses")
        else:
            value = uses[0].split(" #", 1)[0].strip()
            if (not value) or value[:1] in ("'", '"', "|", ">", "{", "[", "&", "*", "!") or value.startswith("<<"):
                errors["G-Y4"].append("keel-gate checkout uses must be one plain unquoted value")
        with_pairs = _keys(checkout, 10)
        with_keys = dict(with_pairs)
        names = sorted(key for key, _ in with_pairs)
        if names != sorted(CHECKOUT_WITH):
            # ref:, repository:, path: and others change what HEAD is (Security F-02).
            errors["G-Y4"].append("checkout with: keys are %s, expected exactly %s" % (names, sorted(CHECKOUT_WITH)))
        if with_keys.get("fetch-depth") != "0":
            errors["G-Y4"].append("checkout must use fetch-depth: 0")
        if with_keys.get("persist-credentials") != "false":
            errors["G-Y4"].append("checkout must use persist-credentials: false")
        extra = [key for key, _ in _keys(checkout, 8) if key not in ("uses", "with")]
        if extra:
            errors["G-Y4"].append("checkout step has extra keys %s" % extra)
    errors["G-Y4"].extend(checkout_file_problems(text))
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
            timeout=60,
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
        "G-Y4": "the official checkout, once, at a full SHA, the same as every other checkout in checks.yml, and the synthetic pin cases hold",
        "G-Y5": "workflow top-level keys are only name, on, permissions, concurrency, jobs",
        "G-Y6": "keel-gate job has only plain, unrepeated keys",
        "G-Y7": "Gate run: block has no ${{ }} expressions",
    }
    found = yaml_errors(text)
    found["G-Y4"].extend(matrix_issues(text))
    for name, problems in found.items():
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

        # KEEL_MUTATE_BASE differs from GATE_PR_BASE_SHA: the chain still comes
        # from GATE_PR_BASE_SHA (Security F-03).
        s, base, merge = build(case("a10"), pr_edit=lambda s: s.write("docs/a.md", "b\n"))
        code, out = run_step(block, s, "pull_request", merge, base, extra={"KEEL_MUTATE_BASE": merge})
        res("G-A10", (MARKER + " " + base) in out and (MARKER + " " + merge) not in out,
            "base chain follows GATE_PR_BASE_SHA, not KEEL_MUTATE_BASE (exit %s)" % code)
    except Exception as err:  # a broken scratch setup is a failure, not a pass
        res("G-X1", False, "scratch setup failed: %s" % err)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
