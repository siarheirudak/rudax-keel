#!/usr/bin/env python3
"""Every job in scripts/gate-jobs.txt is in the keel-gate needs list and has its R_* env var.

keel-gate reads gate-jobs.txt from the base commit (B16). The needs list may
hold more jobs than gate-jobs.txt, so a job can be added to needs first and to
the list in a later pull request, or dropped from the list first and from
needs later, with both pull requests green (D-353, B-01).
"""

import os
import pathlib
import re
import shutil
import stat
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
TYPES = "types: [opened, synchronize, reopened, edited]"
SCOPE_TYPES = (TYPES, "types: [opened, synchronize, reopened, edited, labeled, unlabeled]")


def fail(message):
    print(message, file=sys.stderr)
    print(
        "how to fix: every job in scripts/gate-jobs.txt must be in the keel-gate needs list of .github/workflows/checks.yml with its R_* env var",
        file=sys.stderr,
    )
    sys.exit(1)


def env_name(job):
    return "R_" + job.upper().replace("-", "_")


def job_blocks(text):
    blocks = {}
    current = None
    buf = []
    for line in text.splitlines(keepends=True):
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            if current is not None:
                blocks[current] = "".join(buf)
            current = match.group(1)
            buf = [line]
        elif current is not None:
            buf.append(line)
    if current is not None:
        blocks[current] = "".join(buf)
    return blocks


class GateJobsError(Exception):
    pass


# Required check names. Each must name exactly one job across all workflows, so
# a decoy job cannot report a second, green check with the same name (Auditor FU-1).
REQUIRED_NAMES = ("keel-gate", "keel-process-files-separate")
names_once = True  # names-once
plain_names = True  # plain-names
labeler_trigger = True  # labeler-trigger
labeler_top_permissions = True  # labeler-top-permissions
labeler_job_permissions = True  # labeler-job-permissions
labeler_job_shape = True  # labeler-job-shape
labeler_sync_labels = True  # labeler-sync-labels
labeler_form = True  # labeler-form


NAME_KEY = re.compile(r"(^|[\s{,])name:(\s*)(.*)$")


def plain_name_errors(workflows):
    """Every name: value must be a plain or simply quoted scalar on its own line.

    A block scalar (| or >), an empty value continued on the next line, a tag
    (!!str), an anchor or alias (& or *) or a double-quoted escape (\\x2d) can
    all resolve to a required name that the text match above cannot see
    (Auditor FU-P2). Today's workflows use none of these forms, so rejecting
    them only fails closed.
    """
    problems = []
    for file in sorted(workflows):
        for number, line in enumerate(workflows[file].splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            match = NAME_KEY.search(line)
            if not match:
                continue
            value = match.group(3).strip()
            bad = (
                not value
                or value[0] in "|>!&*"
                or (value[0] == '"' and ("\\" in value or value.count('"') < 2))
                or (value[0] == "'" and value.count("'") < 2)
            )
            if bad:
                problems.append("{0}:{1}: name: value must be a plain one-line string, got {2!r}".format(file, number, value))
    return problems


def name_errors(workflows):
    """workflows: {file name: text}. Return problems with the required names.

    A check run is named by the job's name:, or by its job id when there is no
    name:. Every name: line with that value counts, quoted or in a flow
    mapping, and so does a job id equal to the name in a file that does not
    also hold the name: line.
    """
    if not names_once:
        return []
    problems = []
    if plain_names:
        problems.extend(plain_name_errors(workflows))
    for want in REQUIRED_NAMES:
        quoted = "[\"']?" + re.escape(want) + "[\"']?"
        # GitHub may match check names without regard to case [U], so a
        # Keel-Gate decoy counts too (Auditor FU-P3).
        name_re = re.compile(r"(^|[\s{,])name:\s*" + quoted + r"\s*($|[,}#])", re.I)
        id_re = re.compile(r"^\s+" + quoted + r":\s*($|#|\{)", re.I)
        hits = []
        ids = []
        for file in sorted(workflows):
            for line in workflows[file].splitlines():
                if line.lstrip().startswith("#"):
                    continue
                if name_re.search(line):
                    hits.append(file)
                if id_re.match(line):
                    ids.append(file)
        if len(hits) != 1:
            problems.append("{0}: name: {1} appears {2} times across workflows, expected 1".format(want, want, len(hits)))
        stray = [file for file in ids if file not in hits]
        if stray or len(ids) > 1:
            problems.append("{0}: a job id {0} also names a check in {1}".format(want, ", ".join(sorted(set(ids)))))
    return problems


def check(listed, checks, scope):
    """Raise GateJobsError when the job list, needs and env lines disagree.

    Return the needs jobs that gate-jobs.txt does not list. keel-gate does not
    enforce them, so main() prints a note (Auditor F4).
    """
    if not listed:
        raise GateJobsError("scripts/gate-jobs.txt is empty")
    if len(listed) != len(set(listed)):
        raise GateJobsError("scripts/gate-jobs.txt lists a job twice")
    if TYPES not in checks.split("\njobs:", 1)[0]:
        raise GateJobsError("checks.yml must include {0}".format(TYPES))
    blocks = job_blocks(checks)
    missing = [job for job in listed if job not in blocks]
    if missing:
        raise GateJobsError("gate list names missing jobs: {0}".format(", ".join(missing)))
    gate = blocks.get("keel-gate", "")
    if "name: keel-gate" not in gate:
        raise GateJobsError("keel-gate job name must be keel-gate")
    needs = re.search(r"^    needs:\s*\[([^\]]+)\]\s*$", gate, re.M)
    if not needs:
        raise GateJobsError("keel-gate job has no needs list")
    needed = [part.strip() for part in needs.group(1).split(",")]
    absent = [job for job in listed if job not in needed]
    if absent:
        raise GateJobsError("gate-jobs.txt jobs not in keel-gate needs: {0}".format(", ".join(absent)))
    for job in listed:
        needle = "{0}: ${{{{ needs.{1}.result }}}}".format(env_name(job), job)
        if needle not in gate:
            raise GateJobsError("missing env {0}".format(needle))
    scope_header = scope.split("\njobs:", 1)[0]
    if not any(item in scope_header for item in SCOPE_TYPES):
        raise GateJobsError(
            "scope.yml must include {0} or {1}".format(SCOPE_TYPES[0], SCOPE_TYPES[1])
        )
    if "name: keel-process-files-separate" not in scope:
        raise GateJobsError("scope job name must be keel-process-files-separate")
    return [job for job in needed if job not in listed]


def _sample(needs, env_jobs):
    env = "".join("          {0}: ${{{{ needs.{1}.result }}}}\n".format(env_name(job), job) for job in env_jobs)
    jobs = "".join("  {0}:\n    runs-on: x\n".format(job) for job in ("a", "b", "c"))
    return (
        "on:\n  pull_request:\n    " + TYPES + "\njobs:\n" + jobs
        + "  keel-gate:\n    name: keel-gate\n    needs: [" + ", ".join(needs) + "]\n"
        + "    steps:\n      - name: Gate\n        env:\n" + env
    )


_LABELER_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_LABELER_WORD = re.compile(r"^[A-Za-z0-9_-]+\Z")
_LABELER_SHA = re.compile(r"^actions/labeler@[0-9a-f]{40}\Z")
_LABELER_UBUNTU = re.compile(r"^ubuntu-[A-Za-z0-9.]+\Z")
_LABELER_TIMEOUT = re.compile(r"^[1-9][0-9]*\Z")
_LABELER_CANON = (
    "name: labeler\n"
    "\n"
    "# Adds the workflow and process-files labels from the paths a pull request\n"
    "# changes, using the rules in .github/labeler.yml. A label is a marker only:\n"
    "# the scope check decides from the paths.\n"
    "# Labels this job adds start no other workflow run. When this job adds the\n"
    "# workflow label, re-run the scope check once.\n"
    "# The job never removes a label. It does not check out code and runs no\n"
    "# commands. Pull requests from forks get read-only access, so the job cannot\n"
    "# label them; add the workflow label by hand there.\n"
    "on:\n"
    "  pull_request:\n"
    "    types: [opened, synchronize, reopened, edited]\n"
    "\n"
    "permissions: {}\n"
    "\n"
    "jobs:\n"
    "  label:\n"
    "    name: labeler\n"
    "    runs-on: ubuntu-24.04\n"
    "    timeout-minutes: 5\n"
    "    permissions:\n"
    "      contents: read\n"
    "      pull-requests: write\n"
    "    steps:\n"
    "      - uses: actions/labeler@bf12e9b00b37c5c0ca2b87b79b2daf7891dbda13 # v7.0.0\n"
    "        with:\n"
    "          sync-labels: false\n"
)
_LABELER_OTHER_SHA = "0123456789abcdef0123456789abcdef01234567"
_LABELER_CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"


class _LMap(object):
    def __init__(self):
        self.pairs = []
        self.dups = []
        self._seen = set()

    def add(self, key, value, line):
        if key in self._seen:
            self.dups.append(line)
            return
        self._seen.add(key)
        self.pairs.append([key, value, line])

    def get(self, key):
        for key_text, value, line in self.pairs:
            if key_text == key:
                return value, line
        return None, None


class _LSeq(object):
    def __init__(self):
        self.items = []


class _LScalar(object):
    def __init__(self, text, line, quoted, flow):
        self.text = text
        self.line = line
        self.quoted = quoted
        self.flow = flow


def _labeler_text(reason, number):
    if number is None:
        return "labeler.yml: {0}".format(reason)
    return "labeler.yml: {0} (line {1})".format(reason, number)


def _labeler_path_problem(root):
    current = os.fspath(root)
    parts = ((".github", True), ("workflows", True), ("labeler.yml", False))
    try:
        for name, want_dir in parts:
            current = os.path.join(current, name)
            try:
                info = os.lstat(current)
            except OSError:
                return "labeler form: the workflow path is missing"
            if stat.S_ISLNK(info.st_mode):
                return "labeler form: a path part is a symlink"
            if want_dir:
                if not stat.S_ISDIR(info.st_mode):
                    return "labeler form: a path part is not a directory"
            elif not stat.S_ISREG(info.st_mode):
                return "labeler form: the workflow path is not a regular file"
    except Exception:
        return "labeler form: the workflow path cannot be read"
    return None


def _labeler_check_root(root):
    try:
        problem = _labeler_path_problem(root)
        if problem is not None:
            if labeler_form:
                return [_labeler_text(problem, None)]
            return []
        path = os.path.join(os.fspath(root), ".github", "workflows", "labeler.yml")
        with open(path, "rb") as handle:
            data = handle.read()
    except Exception:
        if labeler_form:
            return [_labeler_text("labeler form: the workflow path cannot be read", None)]
        return []
    return _labeler_check_bytes(data)


def _labeler_check_bytes(data):
    try:
        return _labeler_bytes(data)
    except Exception:
        if labeler_form:
            return [_labeler_text("labeler form: the workflow text cannot be read", None)]
        return []


def _labeler_bytes(data):
    if isinstance(data, str):
        try:
            data = data.encode("ascii")
        except UnicodeEncodeError:
            if labeler_form:
                return [_labeler_text("labeler form: bytes are not ascii", None)]
            return []
    else:
        data = bytes(data)
    if any(byte > 127 for byte in data):
        if labeler_form:
            index = next(pos for pos, byte in enumerate(data) if byte > 127)
            return [_labeler_text("labeler form: bytes are not ascii", data[:index].count(b"\n") + 1)]
        return []
    if b"\r" in data:
        if labeler_form:
            return [_labeler_text("labeler form: line ending is not lf", data[: data.find(b"\r")].count(b"\n") + 1)]
        return []
    if b"\t" in data:
        if labeler_form:
            return [_labeler_text("labeler form: a line contains a tab", data[: data.find(b"\t")].count(b"\n") + 1)]
        return []
    root, form_problems = _labeler_parse(data.decode("ascii"))
    return _labeler_lines(root, form_problems)


def _labeler_split_hash(text):
    quote = ""
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            continue
        if char == "#":
            if index > 0 and text[index - 1] == " ":
                return text[:index].rstrip(), None
            return None, "labeler form: hash in value"
    return text.rstrip(), None


def _labeler_unquote(value):
    if len(value) < 2 or value[0] not in "\"'" or value[-1] != value[0]:
        return None
    inner = value[1:-1]
    if "\\" in inner or value[0] in inner:
        return None
    return inner


def _labeler_flow_list(value):
    if len(value) < 2 or value[0] != "[" or value[-1] != "]":
        return None
    inner = value[1:-1].strip()
    if inner == "":
        return []
    words = []
    for part in inner.split(","):
        word = part.strip()
        if _LABELER_WORD.match(word) is None:
            return None
        words.append(word)
    return words


def _labeler_key(text):
    body, hash_error = _labeler_split_hash(text)
    if hash_error:
        return ("bad", hash_error)
    if not body or ":" not in body:
        return ("bad", "labeler form: unrecognised line")
    key, _sep, rest = body.partition(":")
    if _LABELER_KEY.match(key) is None:
        return ("bad", "labeler form: unrecognised line")
    value = rest.lstrip(" ")
    if value == "":
        return ("ok", key, None)
    if "#" in value:
        return ("bad", "labeler form: hash in value")
    if value.startswith(("|", ">", "!", "&", "*")):
        return ("bad", "labeler form: forbidden form")
    if value.startswith("{"):
        if not (key == "permissions" and value == "{}"):
            return ("bad", "labeler form: forbidden form")
        return ("ok", key, ("scalar", "{}", False, "map"))
    if value.startswith("["):
        if key != "types" or _labeler_flow_list(value) is None:
            return ("bad", "labeler form: forbidden form")
        return ("ok", key, ("scalar", value, False, "list"))
    if value[:1] in "\"'":
        inner = _labeler_unquote(value)
        if inner is None:
            return ("bad", "labeler form: forbidden form")
        return ("ok", key, ("scalar", inner, True, None))
    return ("ok", key, ("scalar", value, False, None))


def _labeler_scalar(parsed, number):
    if parsed is None:
        return None
    _kind, text, quoted, flow = parsed
    return _LScalar(text, number, quoted, flow)


def _labeler_container(frame):
    if frame[0] == "map":
        return frame[1], frame[2]
    return frame[3], frame[2] + 2


def _labeler_place_key(stack, indent, parsed, add_form, number):
    key = parsed[1]
    scalar = _labeler_scalar(parsed[2], number)
    while True:
        container, key_indent = _labeler_container(stack[-1])
        if key_indent == indent:
            container.add(key, scalar, number)
            return
        if key_indent < indent:
            break
        if len(stack) == 1:
            add_form("labeler form: indentation is not a two-space step", number)
            return
        stack.pop()
    parent, parent_indent = _labeler_container(stack[-1])
    if indent != parent_indent + 2 or not parent.pairs or parent.pairs[-1][1] is not None:
        add_form("labeler form: indentation is not a two-space step", number)
        return
    child = _LMap()
    parent.pairs[-1][1] = child
    child.add(key, scalar, number)
    stack.append(("map", child, indent))


def _labeler_place_item(stack, dash_indent, parsed, add_form, number):
    key = parsed[1]
    scalar = _labeler_scalar(parsed[2], number)
    while len(stack) > 1:
        top = stack[-1]
        if top[0] == "seq" and top[2] == dash_indent:
            item = _LMap()
            item.add(key, scalar, number)
            top[1].items.append(item)
            stack[-1] = ("seq", top[1], dash_indent, item)
            return
        if top[0] == "seq" and top[2] < dash_indent:
            break
        if top[0] == "map" and top[2] <= dash_indent - 2:
            break
        stack.pop()
    top = stack[-1]
    if top[0] != "map" or top[2] != dash_indent - 2:
        add_form("labeler form: indentation is not a two-space step", number)
        return
    parent = top[1]
    if not parent.pairs or parent.pairs[-1][1] is not None:
        add_form("labeler form: indentation is not a two-space step", number)
        return
    seq = _LSeq()
    item = _LMap()
    item.add(key, scalar, number)
    seq.items.append(item)
    parent.pairs[-1][1] = seq
    stack.append(("seq", seq, dash_indent, item))


def _labeler_parse(text):
    root = _LMap()
    stack = [("map", root, 0)]
    problems = []

    def add_form(reason, number):
        problems.append((reason, number))

    for number, raw in enumerate(text.splitlines(), 1):
        if raw.strip() == "" or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        body = raw[indent:]
        if indent % 2:
            add_form("labeler form: indentation is not a two-space step", number)
            continue
        if body.startswith("---") or body.startswith("..."):
            add_form("labeler form: extra document marker", number)
            continue
        if body.startswith("%"):
            add_form("labeler form: directive", number)
            continue
        if body.startswith("?"):
            add_form("labeler form: explicit key", number)
            continue
        if body.startswith("<<"):
            add_form("labeler form: merge key", number)
            continue
        if body[:1] in "\"'":
            add_form("labeler form: quoted key", number)
            continue
        if body.startswith("- "):
            parsed = _labeler_key(body[2:])
            if parsed[0] != "ok":
                add_form(parsed[1], number)
                continue
            _labeler_place_item(stack, indent, parsed, add_form, number)
            continue
        if body.startswith("-"):
            add_form("labeler form: unrecognised line", number)
            continue
        parsed = _labeler_key(body)
        if parsed[0] != "ok":
            add_form(parsed[1], number)
            continue
        _labeler_place_key(stack, indent, parsed, add_form, number)
    return root, problems


def _labeler_walk(node, dups, scalars):
    if isinstance(node, _LMap):
        dups.extend(node.dups)
        for _key, value, _line in node.pairs:
            if value is not None:
                _labeler_walk(value, dups, scalars)
    elif isinstance(node, _LSeq):
        for item in node.items:
            _labeler_walk(item, dups, scalars)
    elif isinstance(node, _LScalar):
        scalars.append(node)


def _labeler_one_job(root):
    jobs, _line = root.get("jobs")
    if not isinstance(jobs, _LMap) or len(jobs.pairs) != 1:
        return None
    job = jobs.pairs[0][1]
    if not isinstance(job, _LMap):
        return None
    return job


def _labeler_steps(root):
    jobs, _line = root.get("jobs")
    found = []
    if not isinstance(jobs, _LMap):
        return found
    for _name, job, _line in jobs.pairs:
        if not isinstance(job, _LMap):
            continue
        steps, _sline = job.get("steps")
        if not isinstance(steps, _LSeq):
            continue
        found.extend(steps.items)
    return found


def _labeler_trigger(root):
    reason = "labeler trigger: trigger is not a pull request block with a types list"
    node, line = root.get("on")
    if not isinstance(node, _LMap):
        number = node.line if isinstance(node, _LScalar) else None
        return [_labeler_text(reason, number)]
    if len(node.pairs) != 1 or node.pairs[0][0] != "pull_request":
        number = node.pairs[0][2] if node.pairs else line
        return [_labeler_text(reason, number)]
    child = node.pairs[0][1]
    if not isinstance(child, _LMap) or len(child.pairs) != 1 or child.pairs[0][0] != "types":
        return [_labeler_text(reason, node.pairs[0][2])]
    types = child.pairs[0][1]
    if not isinstance(types, _LScalar) or types.flow != "list" or types.quoted:
        return [_labeler_text(reason, child.pairs[0][2])]
    return []


def _labeler_top_permissions(root):
    reason = "labeler top permissions: top permissions are not empty"
    node, line = root.get("permissions")
    if isinstance(node, _LScalar) and not node.quoted and node.text == "{}":
        return []
    number = node.line if isinstance(node, _LScalar) else line
    return [_labeler_text(reason, number)]


def _labeler_job_permissions(root):
    job = _labeler_one_job(root)
    if job is None:
        return []
    reason = "labeler job permissions: job permissions are not the allowed pair"
    node, line = job.get("permissions")
    if not isinstance(node, _LMap):
        number = node.line if isinstance(node, _LScalar) else line
        return [_labeler_text(reason, number)]
    got = []
    for key, value, key_line in node.pairs:
        if not isinstance(value, _LScalar) or value.quoted:
            return [_labeler_text(reason, key_line)]
        got.append((key, value.text))
    want = [("contents", "read"), ("pull-requests", "write")]
    if len(got) != 2 or sorted(got) != sorted(want):
        number = node.pairs[0][2] if node.pairs else line
        return [_labeler_text(reason, number)]
    return []


def _labeler_inputs(root):
    matched = []
    for item in _labeler_steps(root):
        uses, _line = item.get("uses")
        if isinstance(uses, _LScalar) and uses.text.startswith("actions/labeler@"):
            matched.append(item)
    if len(matched) != 1:
        return []
    step = matched[0]
    reason = "labeler inputs: the labeler step does not set only sync-labels false"
    node, line = step.get("with")
    if not isinstance(node, _LMap) or len(node.pairs) != 1 or node.pairs[0][0] != "sync-labels":
        number = line
        if isinstance(node, _LScalar):
            number = node.line
        elif isinstance(node, _LMap) and node.pairs:
            number = node.pairs[0][2]
        if number is None and step.pairs:
            number = step.pairs[0][2]
        return [_labeler_text(reason, number)]
    value = node.pairs[0][1]
    if not isinstance(value, _LScalar) or value.quoted or value.text != "false":
        number = value.line if isinstance(value, _LScalar) else node.pairs[0][2]
        return [_labeler_text(reason, number)]
    return []


def _labeler_shape(root):
    lines = []
    allowed_top = {"name", "on", "permissions", "jobs"}
    allowed_job = {"name", "runs-on", "timeout-minutes", "permissions", "steps"}
    for key, _value, line in root.pairs:
        if key not in allowed_top:
            lines.append(_labeler_text("labeler job shape: a key is outside the allowed set", line))
    name, name_line = root.get("name")
    if not isinstance(name, _LScalar) or name.quoted or name.text == "":
        number = name.line if isinstance(name, _LScalar) else name_line
        lines.append(_labeler_text("labeler job shape: a key is outside the allowed set", number))
    jobs, jobs_line = root.get("jobs")
    job = None
    if not isinstance(jobs, _LMap) or len(jobs.pairs) != 1 or not isinstance(jobs.pairs[0][1], _LMap):
        lines.append(_labeler_text("labeler job shape: the workflow does not have one labeler step", jobs_line))
    else:
        job = jobs.pairs[0][1]
    if isinstance(job, _LMap):
        for key, _value, line in job.pairs:
            if key not in allowed_job:
                lines.append(_labeler_text("labeler job shape: a key is outside the allowed set", line))
        for required in ("name", "runs-on", "timeout-minutes", "steps"):
            node, _line = job.get(required)
            if node is None:
                lines.append(_labeler_text("labeler job shape: a key is outside the allowed set", None))
        runs, _runs_line = job.get("runs-on")
        if runs is not None and (
            not isinstance(runs, _LScalar) or runs.quoted or _LABELER_UBUNTU.match(runs.text) is None
        ):
            number = runs.line if isinstance(runs, _LScalar) else _runs_line
            lines.append(_labeler_text("labeler job shape: runs-on is not one ubuntu label", number))
        timeout, _time_line = job.get("timeout-minutes")
        if timeout is not None and (
            not isinstance(timeout, _LScalar) or timeout.quoted or _LABELER_TIMEOUT.match(timeout.text) is None
        ):
            number = timeout.line if isinstance(timeout, _LScalar) else _time_line
            lines.append(_labeler_text("labeler job shape: timeout-minutes is not a positive integer", number))
        steps, steps_line = job.get("steps")
        if isinstance(steps, _LSeq):
            if len(steps.items) != 1:
                lines.append(_labeler_text("labeler job shape: the workflow does not have one labeler step", steps_line))
            for item in steps.items:
                for key, _value, line in item.pairs:
                    if key not in ("uses", "with"):
                        lines.append(_labeler_text("labeler job shape: a key is outside the allowed set", line))
                uses, uses_line = item.get("uses")
                if (
                    not isinstance(uses, _LScalar)
                    or uses.quoted
                    or _LABELER_SHA.match(uses.text) is None
                ):
                    number = uses.line if isinstance(uses, _LScalar) else uses_line
                    lines.append(_labeler_text("labeler job shape: the step is not the labeler action", number))
        elif steps is not None:
            lines.append(_labeler_text("labeler job shape: the workflow does not have one labeler step", steps_line))
    scalars = []
    _labeler_walk(root, [], scalars)
    for scalar in scalars:
        if "${{" in scalar.text:
            lines.append(_labeler_text("labeler job shape: an expression is present", scalar.line))
    return lines


def _labeler_lines(root, form_problems):
    lines = []
    if labeler_form:
        dups = []
        _labeler_walk(root, dups, [])
        ordered = [(number or 0, index, reason, number) for index, (reason, number) in enumerate(form_problems)]
        ordered.extend(
            (number or 0, len(form_problems) + index, "labeler form: duplicate key", number)
            for index, number in enumerate(dups)
        )
        for _key, _index, reason, number in sorted(ordered):
            lines.append(_labeler_text(reason, number))
    if labeler_trigger:
        lines.extend(_labeler_trigger(root))
    if labeler_top_permissions:
        lines.extend(_labeler_top_permissions(root))
    if labeler_job_permissions:
        lines.extend(_labeler_job_permissions(root))
    if labeler_sync_labels:
        lines.extend(_labeler_inputs(root))
    if labeler_job_shape:
        lines.extend(_labeler_shape(root))
    return lines


def _labeler_edit(old, new):
    if _LABELER_CANON.count(old) != 1:
        raise RuntimeError("canon edit")
    return _LABELER_CANON.replace(old, new, 1)


def _labeler_byte_cases():
    uses = "      - uses: actions/labeler@{0} # v7.0.0\n".format(
        "bf12e9b00b37c5c0ca2b87b79b2daf7891dbda13"
    )
    other_uses = "      - uses: actions/labeler@{0} # v1.2.3\n".format(_LABELER_OTHER_SHA)
    checkout = "      - uses: actions/checkout@{0} # v4\n".format(_LABELER_CHECKOUT_SHA)
    on_block = "on:\n  pull_request:\n    types: [opened, synchronize, reopened, edited]\n"
    types_line = "    types: [opened, synchronize, reopened, edited]\n"
    return (
        ("GJ-LH1 canonical shape", _LABELER_CANON, True),
        ("GJ-LH2 different labeler sha and version comment", _labeler_edit(uses, other_uses), True),
        ("GJ-LH3 different types list", _labeler_edit(types_line, "    types: [opened, closed]\n"), True),
        (
            "GJ-LH4 job permissions in the other order",
            _labeler_edit(
                "      contents: read\n      pull-requests: write\n",
                "      pull-requests: write\n      contents: read\n",
            ),
            True,
        ),
        ("GJ-LA4 crlf line ending", _LABELER_CANON.replace("\n", "\r\n", 1), False),
        ("GJ-LA5 tab", _labeler_edit("runs-on: ubuntu-24.04", "runs-on:\tubuntu-24.04"), False),
        ("GJ-LA6 non-ascii character", _LABELER_CANON + "\u00e9", False),
        ("GJ-LA7 non-utf8 bytes", _LABELER_CANON.encode("ascii") + b"\xff", False),
        ("GJ-LA8 hash inside a value", _labeler_edit("runs-on: ubuntu-24.04", "runs-on: ubuntu-24.04#extra"), False),
        (
            "GJ-LA9 duplicate top permissions",
            _labeler_edit("permissions: {}\n", "permissions: {}\npermissions: write-all\n"),
            False,
        ),
        (
            "GJ-LA10 duplicate contents",
            _labeler_edit("      contents: read\n", "      contents: read\n      contents: write\n"),
            False,
        ),
        ("GJ-LA11 duplicate on", _labeler_edit(on_block, on_block + "on:\n  pull_request:\n    types: [opened]\n"), False),
        (
            "GJ-LA12 duplicate pull request key",
            _labeler_edit(
                "  pull_request:\n" + types_line,
                "  pull_request:\n" + types_line + "  pull_request:\n    types: [opened]\n",
            ),
            False,
        ),
        (
            "GJ-LA13 plain continuation",
            _labeler_edit("          sync-labels: false\n", "          sync-labels: false\n            continued\n"),
            False,
        ),
        ("GJ-LA14 explicit key", _labeler_edit("    name: labeler\n", "    ? name\n    name: labeler\n"), False),
        ("GJ-LA15 directive", "%YAML 1.1\n" + _LABELER_CANON, False),
        ("GJ-LA16 merge key", _labeler_edit("    name: labeler\n", "    <<: *base\n    name: labeler\n"), False),
        ("GJ-LA17 quoted key", _labeler_edit("  pull_request:\n", '  "pull_request_target":\n'), False),
        ("GJ-LA18 flow trigger", _labeler_edit(on_block, "on: [pull_request_target]\n"), False),
        ("GJ-LA19 pull request target", _labeler_edit("  pull_request:\n", "  pull_request_target:\n"), False),
        (
            "GJ-LA20 second trigger",
            _labeler_edit(types_line, types_line + "  pull_request_target:\n" + types_line),
            False,
        ),
        (
            "GJ-LA21 commented trigger",
            _labeler_edit("  pull_request:\n", "  # pull_request:\n  pull_request_target:\n"),
            False,
        ),
        ("GJ-LA22 scalar trigger", _labeler_edit(on_block, "on: pull_request\n"), False),
        ("GJ-LA23 top write all", _labeler_edit("permissions: {}", "permissions: write-all"), False),
        ("GJ-LA24 top permissions removed", _labeler_edit("permissions: {}\n", ""), False),
        ("GJ-LA25 top read all", _labeler_edit("permissions: {}", "permissions: read-all"), False),
        (
            "GJ-LA26 top permissions block",
            _labeler_edit("permissions: {}\n", "permissions:\n  contents: read\n"),
            False,
        ),
        ("GJ-LA27 contents write", _labeler_edit("contents: read", "contents: write"), False),
        (
            "GJ-LA28 third job permission",
            _labeler_edit("      pull-requests: write\n", "      pull-requests: write\n      actions: write\n"),
            False,
        ),
        (
            "GJ-LA29 job permissions scalar",
            _labeler_edit(
                "    permissions:\n      contents: read\n      pull-requests: write\n",
                "    permissions: write-all\n",
            ),
            False,
        ),
        ("GJ-LA30 contents removed", _labeler_edit("      contents: read\n", ""), False),
        ("GJ-LA31 sync labels true", _labeler_edit("sync-labels: false", "sync-labels: true"), False),
        (
            "GJ-LA32 extra token input",
            _labeler_edit(
                "          sync-labels: false\n",
                "          sync-labels: false\n          repo-token: ${{ secrets.LABEL_TOKEN }}\n",
            ),
            False,
        ),
        ("GJ-LA33 with block removed", _labeler_edit("        with:\n          sync-labels: false\n", ""), False),
        ("GJ-LA34 quoted sync labels", _labeler_edit("sync-labels: false", 'sync-labels: "false"'), False),
        ("GJ-LA35 checkout step", _labeler_edit("    steps:\n", "    steps:\n" + checkout), False),
        ("GJ-LA36 run step", _labeler_edit("    steps:\n", "    steps:\n      - run: echo labeled\n"), False),
        ("GJ-LA37 job if", _labeler_edit("    timeout-minutes: 5\n", "    timeout-minutes: 5\n    if: false\n"), False),
        (
            "GJ-LA38 step continue on error",
            _labeler_edit("        with:\n", "        continue-on-error: true\n        with:\n"),
            False,
        ),
        (
            "GJ-LA39 job continue on error",
            _labeler_edit("    timeout-minutes: 5\n", "    timeout-minutes: 5\n    continue-on-error: true\n"),
            False,
        ),
        ("GJ-LA40 step if", _labeler_edit("        with:\n", "        if: false\n        with:\n"), False),
    )


def _labeler_symlink_rejected(kind):
    folder = tempfile.mkdtemp(prefix="keel-labeler-")
    try:
        payload = _LABELER_CANON.encode("ascii")
        if kind == "github":
            real = os.path.join(folder, "real-dir")
            os.makedirs(os.path.join(real, "workflows"))
            with open(os.path.join(real, "workflows", "labeler.yml"), "wb") as handle:
                handle.write(payload)
            os.symlink(real, os.path.join(folder, ".github"))
        elif kind == "workflows":
            os.makedirs(os.path.join(folder, ".github"))
            real = os.path.join(folder, "real-workflows")
            os.makedirs(real)
            with open(os.path.join(real, "labeler.yml"), "wb") as handle:
                handle.write(payload)
            os.symlink(real, os.path.join(folder, ".github", "workflows"))
        elif kind == "file":
            os.makedirs(os.path.join(folder, ".github", "workflows"))
            real = os.path.join(folder, "real-file.yml")
            with open(real, "wb") as handle:
                handle.write(payload)
            os.symlink(real, os.path.join(folder, ".github", "workflows", "labeler.yml"))
        else:
            raise RuntimeError("kind")
        return bool(_labeler_check_root(folder))
    finally:
        shutil.rmtree(folder)


def _labeler_self_test():
    bad = []
    for name, data, want in _labeler_byte_cases():
        try:
            ok = not _labeler_check_bytes(data)
        except Exception:
            bad.append(name)
            continue
        if ok != want:
            bad.append(name)
    for name, kind in (
        ("GJ-LA1 symlinked github directory", "github"),
        ("GJ-LA2 symlinked workflows directory", "workflows"),
        ("GJ-LA3 symlinked workflow file", "file"),
    ):
        try:
            rejected = _labeler_symlink_rejected(kind)
        except Exception:
            bad.append(name)
            continue
        if not rejected:
            bad.append(name)
    return bad


def _labeler_fail(lines):
    for line in lines:
        print(line, file=sys.stderr)
    print(
        "how to fix: .github/workflows/labeler.yml must keep its trigger, permissions and single step",
        file=sys.stderr,
    )
    sys.exit(1)

def self_test():
    """Cases for the relaxed rule. Return a list of failed case names."""
    scope = "on:\n  pull_request_target:\n    " + TYPES + "\njobs:\n  x:\n    name: keel-process-files-separate\n"
    cases = [
        ("GJ-H1 same list", ["a", "b"], _sample(["a", "b"], ["a", "b"]), True),
        ("GJ-H2 needs has an extra job", ["a"], _sample(["a", "b"], ["a", "b"]), True),
        ("GJ-H3 needs in another order", ["a", "b"], _sample(["b", "a"], ["a", "b"]), True),
        ("GJ-A1 listed job not in needs", ["a", "c"], _sample(["a", "b"], ["a", "b", "c"]), False),
        ("GJ-A2 listed job has no env line", ["a", "b"], _sample(["a", "b"], ["a"]), False),
        ("GJ-A3 empty list", [], _sample(["a"], ["a"]), False),
        ("GJ-A4 listed job is not a job", ["a", "z"], _sample(["a", "z"], ["a", "z"]), False),
        ("GJ-A5 duplicate listed job", ["a", "a"], _sample(["a"], ["a"]), False),
    ]
    bad = []
    for name, listed, checks, want in cases:
        try:
            check(listed, checks, scope)
            ok = True
        except GateJobsError:
            ok = False
        if ok != want:
            bad.append(name)
    try:
        extra = check(["a"], _sample(["a", "b", "c"], ["a"]), scope)
    except GateJobsError:
        extra = None
    if extra != ["b", "c"]:
        bad.append("GJ-N1 unlisted needs jobs are reported")
    good = {"checks.yml": "jobs:\n  keel-gate:\n    name: keel-gate\n", "scope.yml": "jobs:\n  scope:\n    name: keel-process-files-separate\n"}
    name_cases = [
        ("GJ-H4 each required name once", good, True),
        ("GJ-A6 decoy job name in another workflow", dict(good, **{"x.yml": "jobs:\n  fake:\n    name: keel-gate\n"}), False),
        ("GJ-A7 decoy quoted name in the same workflow", {"checks.yml": good["checks.yml"] + "  fake:\n    name: 'keel-gate'\n", "scope.yml": good["scope.yml"]}, False),
        ("GJ-A8 decoy flow-style name", dict(good, **{"x.yml": "jobs:\n  fake: {name: keel-process-files-separate, runs-on: x}\n"}), False),
        ("GJ-A9 decoy job id with no name:", dict(good, **{"x.yml": "jobs:\n  keel-gate:\n    runs-on: x\n"}), False),
        ("GJ-A10 required name missing", {"checks.yml": good["checks.yml"]}, False),
        ("GJ-A11 decoy name as a block scalar", dict(good, **{"x.yml": "jobs:\n  fake:\n    name: >-\n      keel-gate\n"}), False),
        ("GJ-A12 decoy name on the next line", dict(good, **{"x.yml": "jobs:\n  fake:\n    name:\n      keel-gate\n"}), False),
        ("GJ-A13 decoy name with an escape", dict(good, **{"x.yml": "jobs:\n  fake:\n    name: \"keel\\x2dgate\"\n"}), False),
        ("GJ-A14 decoy name with a tag", dict(good, **{"x.yml": "jobs:\n  fake:\n    name: !!str keel-gate\n"}), False),
        ("GJ-A15 decoy name through an alias", dict(good, **{"x.yml": "env: {K: &kg keel-gate}\njobs:\n  fake:\n    name: *kg\n"}), False),
        ("GJ-A16 decoy name in another case", dict(good, **{"x.yml": "jobs:\n  fake:\n    name: Keel-Gate\n"}), False),
        ("GJ-A17 decoy in an upper-case .YML file", dict(good, **{"X.YML": "jobs:\n  fake:\n    name: keel-gate\n"}), False),
        ("GJ-H5 other plain and expression names are fine", dict(good, **{"x.yml": "jobs:\n  a:\n    name: build ${{ matrix.k }}\n    steps:\n      - name: 'quoted step'\n"}), True),
    ]
    for name, workflows, want in name_cases:
        if (not name_errors(workflows)) != want:
            bad.append(name)
    six = SCOPE_TYPES[1]
    scope_cases = [
        ("GJ-H6 scope with the label triggers", "on:\n  pull_request_target:\n    " + six + "\njobs:\n  x:\n    name: keel-process-files-separate\n", True),
        ("GJ-A18 scope label triggers without edited", "on:\n  pull_request_target:\n    types: [opened, synchronize, reopened, labeled, unlabeled]\njobs:\n  x:\n    name: keel-process-files-separate\n", False),
        ("GJ-A20 scope with an extra type", "on:\n  pull_request_target:\n    types: [opened, synchronize, reopened, edited, labeled, unlabeled, closed]\njobs:\n  x:\n    name: keel-process-files-separate\n", False),
    ]
    sample = _sample(["a", "b"], ["a", "b"])
    for name, scope_text, want in scope_cases:
        try:
            check(["a", "b"], sample, scope_text)
            ok = True
        except GateJobsError:
            ok = False
        if ok != want:
            bad.append(name)
    try:
        check(["a", "b"], sample.replace(TYPES, six, 1), scope)
        bad.append("GJ-A19 checks with the label triggers")
    except GateJobsError:
        pass
    try:
        bad.extend(_labeler_self_test())
    except Exception:
        bad.append("GJ-LA0 labeler rows")
    return bad


def main():
    bad = self_test()
    if bad:
        fail("self-test failed: {0}".format(", ".join(bad)))
    labeler_lines = _labeler_check_root(ROOT)
    if labeler_lines:
        _labeler_fail(labeler_lines)
    listed = [
        line.strip()
        for line in (ROOT / "scripts" / "gate-jobs.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    checks = (ROOT / ".github" / "workflows" / "checks.yml").read_text(encoding="utf-8")
    scope = (ROOT / ".github" / "workflows" / "scope.yml").read_text(encoding="utf-8")
    try:
        extra = check(listed, checks, scope)
    except GateJobsError as err:
        fail(str(err))
    folder = ROOT / ".github" / "workflows"
    workflows = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(folder.iterdir())
        if path.suffix.lower() in (".yml", ".yaml") and path.is_file()
    }
    problems = name_errors(workflows)
    if problems:
        fail("; ".join(problems))
    if extra:
        print("NOTE: keel-gate needs has jobs not in scripts/gate-jobs.txt: {0} (not enforced by keel-gate)".format(", ".join(extra)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
