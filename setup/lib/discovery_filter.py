#!/usr/bin/env python3
"""Host accept-or-discard pipeline for discoveries and ADRs.

Roles may append candidates. This module promotes only when the caller
says the iteration is finished. Accepted files land under
.keel/memory/discoveries or .keel/memory/adr. Rejected candidates are
deleted. There is no proposed queue.
"""

import datetime
import json
import os
import re
import shutil
import sys
import uuid

import discovery_judge

MAX_BYTES_DEFAULT = 32 * 1024
MIN_BODY_DEFAULT = 40
SEVERITIES = ("critical", "normal", "low")
KINDS = ("discovery", "adr", "abort-cause")
CANDIDATE_KINDS = ("discovery", "adr")
BYPASS_PHRASES = (
    "ignore previous",
    "ignore all previous",
    "ignore prior",
    "disregard previous",
    "disregard prior",
    "bypass gate",
    "bypass the gate",
    "bypass the filter",
    "exfiltrate",
    "do not apply the gate",
    "skip the acceptance",
    "skip the filter",
    "override the filter",
    "set aside the gate",
    "tell the auditor",
    "tell the developer",
    "игнорируй предыдущ",
    "обойди проверку",
    "обойди фильтр",
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
KNOWN_KEYS = frozenset((
    "id", "title", "date", "tags", "paths", "severity", "kind",
    "rule", "superseded_by", "task_id",
))
REQUIRED = ("id", "title", "date", "tags", "paths", "severity", "kind")


class FilterError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def pattern_filter_on():
    return True  # disc-pattern-on


def significance_on():
    return True  # disc-significance-on


def path_check_on():
    return True  # disc-path-check


def size_cap_on():
    return True  # disc-size-cap


def symlink_refuse_on():
    return True  # disc-symlink-refuse


def discard_deletes():
    return True  # disc-no-queue


def redact_audit():
    return True  # disc-audit-redact


def schema_check_on():
    return True  # disc-schema-on


def audit_failures():
    return True  # disc-audit-failures


def promote_order_on():
    return True  # disc-promote-order


def critical_needs_d2():
    return True  # disc-critical-d2


def max_bytes(env=None):
    if env is None:
        env = os.environ
    raw = env.get("KEEL_DISCOVERY_MAX_BYTES", str(MAX_BYTES_DEFAULT))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return MAX_BYTES_DEFAULT


def min_body(env=None):
    if env is None:
        env = os.environ
    raw = env.get("KEEL_DISCOVERY_MIN_BODY", str(MIN_BODY_DEFAULT))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return MIN_BODY_DEFAULT


def candidates_dir(work):
    return os.path.join(work, ".keel", "candidates")


def accepted_dir(work, kind):
    name = "adr" if kind == "adr" else "discoveries"
    return os.path.join(work, ".keel", "memory", name)


def size_cap_applies(path, work):
    root = os.path.realpath(candidates_dir(work))
    parent = os.path.realpath(os.path.dirname(path))
    return parent == root


def _split_front_matter(text):
    if not text.startswith("---\n"):
        raise FilterError("schema")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise FilterError("schema")
    raw = text[4:end]
    body = text[end + 5 :]
    return raw, body


def _parse_value(raw):
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if inner == "":
            return []
        return [part.strip() for part in inner.split(",") if part.strip()]
    return text


def parse_front_matter(text):
    raw, body = _split_front_matter(text)
    meta = {}
    key = None
    for line in raw.splitlines():
        if line.startswith("  - ") or line.startswith("- "):
            if key not in ("paths", "tags"):
                raise FilterError("schema")
            item = line.split("-", 1)[1].strip()
            meta.setdefault(key, [])
            if not isinstance(meta[key], list):
                raise FilterError("schema")
            meta[key].append(item)
            continue
        if ":" not in line:
            raise FilterError("schema")
        name, rest = line.split(":", 1)
        name = name.strip()
        if name in meta:
            raise FilterError("schema")
        if name not in KNOWN_KEYS:
            raise FilterError("schema")
        value = _parse_value(rest)
        if name in ("paths", "tags") and isinstance(value, str):
            if value == "":
                value = []
            else:
                value = [part.strip() for part in value.split(",") if part.strip()]
        meta[name] = value
        key = name
    if schema_check_on():
        for name in REQUIRED:
            if name not in meta:
                raise FilterError("schema")
        if not isinstance(meta["title"], str) or meta["title"].strip() == "":
            raise FilterError("schema")
        if not isinstance(meta["id"], str) or not ID_RE.match(meta["id"]):
            raise FilterError("schema")
        if not isinstance(meta["date"], str) or not DATE_RE.match(meta["date"]):
            raise FilterError("schema")
        try:
            datetime.datetime.strptime(meta["date"], "%Y-%m-%d")
        except ValueError:
            raise FilterError("schema")
        if meta["severity"] not in SEVERITIES:
            raise FilterError("schema")
        if meta["kind"] not in CANDIDATE_KINDS:
            raise FilterError("schema")
        if not isinstance(meta["paths"], list) or not isinstance(meta["tags"], list):
            raise FilterError("schema")
    else:
        meta.setdefault("id", "raw-" + uuid.uuid4().hex[:8])
        meta.setdefault("title", "untitled")
        meta.setdefault("date", "2026-11-05")
        meta.setdefault("tags", [])
        meta.setdefault("paths", [])
        meta.setdefault("kind", "discovery")
        if meta.get("severity") not in SEVERITIES:
            meta["severity"] = "normal"
        if meta.get("kind") not in CANDIDATE_KINDS:
            meta["kind"] = "discovery"
    meta["body"] = body
    return meta


def _fold(text):
    return text.casefold()


def pattern_hit(meta):
    if not pattern_filter_on():
        return False
    chunks = [
        meta.get("title", ""),
        meta.get("body", ""),
        meta.get("rule", "") or "",
        " ".join(meta.get("tags") or []),
    ]
    folded = _fold("\n".join(chunks))
    for phrase in BYPASS_PHRASES:
        if _fold(phrase) in folded:
            return True
    return False


def _path_inside(work, rel):
    if not isinstance(rel, str) or rel == "":
        return False
    if rel.startswith("/") or "\\" in rel:
        return False
    parts = rel.split("/")
    if ".." in parts:
        return False
    full = os.path.join(work, *parts)
    if os.path.islink(full) or not os.path.exists(full):
        return False
    root = os.path.realpath(work)
    real = os.path.realpath(full)
    return real == root or real.startswith(root + os.sep)


def paths_ok(work, meta):
    if not path_check_on():
        return True
    for rel in meta.get("paths") or []:
        if not _path_inside(work, rel):
            return False
    return True


def significant(meta, env):
    if not significance_on():
        return True
    paths = meta.get("paths") or []
    if paths:
        return True
    rule = meta.get("rule") or ""
    if not str(rule).strip():
        return False
    return len(meta.get("body", "").strip()) >= min_body(env)


def _audit_text(record, env):
    if redact_audit():
        text = json.dumps(record, ensure_ascii=True, sort_keys=True)
        for key, value in env.items():
            upper = key.upper()
            if not value or len(value) < 6:
                continue
            if not any(part in upper for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                continue
            text = text.replace(value, "[REDACTED]")
        return text
    leaked = {}
    for key, value in env.items():
        upper = key.upper()
        if any(part in upper for part in ("KEY", "TOKEN", "SECRET")):
            leaked[key] = value
    record = dict(record)
    record["env"] = leaked
    return json.dumps(record, ensure_ascii=True, sort_keys=True)


def audit(keel, record, env=None):
    if env is None:
        env = os.environ
    verdict = record.get("verdict")
    if verdict in ("reject", "error", "timeout") and not audit_failures():
        return
    log_dir = os.path.join(keel, ".keel", "logs")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "discovery-filter.jsonl")
    line = _audit_text(record, env)
    if "\n" in line or "\r" in line:
        record = dict(record)
        record["reason_code"] = "bad_record"
        line = json.dumps(record, ensure_ascii=True, sort_keys=True)
    with open(path, "a", encoding="ascii") as handle:
        handle.write(line + "\n")


def _record(candidate_id, verdict, reason, probability=None, error_class=None, model=None):
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    return {
        "candidate_id": candidate_id,
        "verdict": verdict,
        "probability": probability,
        "error_class": error_class,
        "reason_code": reason,
        "timestamp": stamp,
        "model": model,
    }


def _reject(path, keel, candidate_id, reason, env, probability=None, error_class=None, model=None, verdict="reject"):
    audit(keel, _record(candidate_id, verdict, reason, probability, error_class, model), env)
    if path and os.path.lexists(path):
        if discard_deletes():
            if not os.path.islink(path):
                os.remove(path)
            else:
                os.remove(path)
        else:
            work = os.path.dirname(os.path.dirname(os.path.dirname(path)))
            proposed = os.path.join(work, ".keel", "proposed")
            os.makedirs(proposed, exist_ok=True)
            shutil.move(path, os.path.join(proposed, os.path.basename(path)))
    return {"status": "reject", "reason": reason}


def _slug(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    return (slug[:40] or "note").strip("-") or "note"


def _id_taken(work, ident):
    for kind in ("discovery", "adr"):
        root = accepted_dir(work, kind)
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(4096)
            if "\nid: {0}\n".format(ident) in "\n" + text:
                return True
    return False


def _write_accepted(work, meta):
    dest_dir = accepted_dir(work, meta["kind"])
    os.makedirs(dest_dir, exist_ok=True)
    name = "{0}-{1}.md".format(meta["date"], _slug(meta["title"]))
    dest = os.path.join(dest_dir, name)
    if os.path.exists(dest):
        dest = os.path.join(dest_dir, "{0}-{1}-{2}.md".format(meta["date"], _slug(meta["title"]), meta["id"]))
    lines = ["---"]
    for key in ("id", "title", "date", "severity", "kind"):
        lines.append("{0}: {1}".format(key, meta[key]))
    for key in ("tags", "paths"):
        value = meta.get(key) or []
        lines.append("{0}: [{1}]".format(key, ", ".join(value)))
    for key in ("rule", "superseded_by", "task_id"):
        if meta.get(key):
            lines.append("{0}: {1}".format(key, meta[key]))
    lines.append("---")
    text = "\n".join(lines) + "\n" + meta.get("body", "")
    if not text.endswith("\n"):
        text += "\n"
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.rename(tmp, dest)
    return dest


def promote_file(path, work, keel, iteration_done=False, owner_yes=None, transport=None, env=None):
    if env is None:
        env = os.environ
    candidate_id = os.path.basename(path)
    if promote_order_on() and not iteration_done:
        audit(keel, _record(candidate_id, "reject", "mid_iteration"), env)
        return {"status": "reject", "reason": "mid_iteration"}
    if not os.path.lexists(path):
        audit(keel, _record(candidate_id, "error", "missing", error_class="missing"), env)
        return {"status": "reject", "reason": "missing"}
    if os.path.islink(path):
        if symlink_refuse_on():
            return _reject(path, keel, candidate_id, "symlink", env)
    if not os.path.isfile(path):
        return _reject(path, keel, candidate_id, "unreadable", env)
    if not size_cap_applies(path, work):
        return _reject(path, keel, candidate_id, "outside_candidates", env)
    size = os.lstat(path).st_size
    if size_cap_on() and size > max_bytes(env):
        return _reject(path, keel, candidate_id, "oversize", env)
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    try:
        meta = parse_front_matter(text)
    except FilterError:
        return _reject(path, keel, candidate_id, "schema", env)
    candidate_id = meta.get("id") or candidate_id
    if schema_check_on() and meta.get("kind") == "abort-cause":
        return _reject(path, keel, candidate_id, "abort_only", env)
    if pattern_hit(meta):
        return _reject(path, keel, candidate_id, "bypass_imperative", env)
    if not paths_ok(work, meta):
        return _reject(path, keel, candidate_id, "path", env)
    if not significant(meta, env):
        return _reject(path, keel, candidate_id, "insignificant", env)
    if schema_check_on() and meta.get("kind") == "adr":
        body = meta.get("body", "")
        for heading in ("## Context", "## Decision", "## Consequences"):
            if heading not in body:
                return _reject(path, keel, candidate_id, "schema", env)
    if _id_taken(work, meta["id"]):
        return _reject(path, keel, candidate_id, "schema", env)
    judged = discovery_judge.decide(text, transport=transport, env=env)
    if not judged["accept"]:
        kind = judged["verdict"] if judged["verdict"] in ("error", "timeout", "reject") else "reject"
        return _reject(
            path, keel, candidate_id, judged["reason"], env,
            probability=judged.get("probability"),
            error_class=judged.get("error_class"),
            model=judged.get("model"),
            verdict=kind,
        )
    if critical_needs_d2() and meta.get("severity") == "critical":
        if owner_yes is not True:
            reason = "needs_d2" if owner_yes is False else "waiting_d2"
            verdict = "reject" if owner_yes is False else "error"
            audit(
                keel,
                _record(candidate_id, verdict, reason, judged.get("probability"), reason, judged.get("model")),
                env,
            )
            if owner_yes is False and os.path.isfile(path) and not os.path.islink(path):
                os.remove(path)
            return {"status": "waiting" if owner_yes is None else "reject", "reason": reason}
    if judged.get("reason") == "judge_skipped":
        model = None
    else:
        model = judged.get("model")
    dest = _write_accepted(work, meta)
    if os.path.isfile(path) and not os.path.islink(path):
        os.remove(path)
    audit(
        keel,
        _record(
            candidate_id, "accept", "accept",
            judged.get("probability"), None, model,
        ),
        env,
    )
    return {"status": "accept", "path": dest, "probability": judged.get("probability")}


def promote_batch(work, keel, iteration_done=False, owner_yes=None, transport=None, env=None):
    root = candidates_dir(work)
    results = []
    if not os.path.isdir(root) or os.path.islink(root):
        return results
    names = sorted(os.listdir(root))
    for name in names:
        path = os.path.join(root, name)
        results.append(promote_file(
            path, work, keel,
            iteration_done=iteration_done,
            owner_yes=owner_yes,
            transport=transport,
            env=env,
        ))
    return results


def render_candidate(meta, body):
    lines = ["---"]
    lines.append("id: {0}".format(meta["id"]))
    lines.append("title: {0}".format(meta["title"]))
    lines.append("date: {0}".format(meta["date"]))
    lines.append("tags: [{0}]".format(", ".join(meta.get("tags") or [])))
    paths = meta.get("paths") or []
    if paths:
        lines.append("paths:")
        for rel in paths:
            lines.append("  - {0}".format(rel))
    else:
        lines.append("paths: []")
    lines.append("severity: {0}".format(meta["severity"]))
    lines.append("kind: {0}".format(meta["kind"]))
    if meta.get("rule"):
        lines.append("rule: {0}".format(meta["rule"]))
    if meta.get("task_id"):
        lines.append("task_id: {0}".format(meta["task_id"]))
    lines.append("---")
    text = "\n".join(lines) + "\n" + body
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_abort_cause(work, keel, task_id, cause):
    """Dossier helper. The only writer of kind abort-cause."""
    os.makedirs(accepted_dir(work, "discovery"), exist_ok=True)
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    ident = "abort-{0}".format(re.sub(r"[^A-Za-z0-9._-]", "-", task_id)[:40])
    meta = {
        "id": ident,
        "title": "Abort cause",
        "date": today,
        "tags": ["abort"],
        "paths": [],
        "severity": "normal",
        "kind": "abort-cause",
        "rule": "dossier",
        "task_id": task_id,
        "body": cause.strip() + "\n",
    }
    dest = _write_accepted(work, meta)
    audit(keel, _record(ident, "accept", "abort_cause", model=None), os.environ)
    return dest


def supersede(work, old_id, new_id):
    found = None
    for kind in ("discovery", "adr"):
        root = accepted_dir(work, kind)
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            text = open(path, encoding="utf-8").read()
            if "\nid: {0}\n".format(old_id) in "\n" + text:
                found = path
                break
    if not found:
        raise FilterError("missing")
    text = open(found, encoding="utf-8").read()
    if "superseded_by:" in text:
        text = re.sub(r"superseded_by:.*", "superseded_by: {0}".format(new_id), text, count=1)
    else:
        text = text.replace("\n---\n", "\nsuperseded_by: {0}\n---\n".format(new_id), 1)
    tmp = found + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.rename(tmp, found)
    return found


def record_owner_answer(work, kind, text):
    if kind == "owner-decisions":
        path = os.path.join(work, "docs", "owner-decisions.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n" + text.strip() + "\n")
        return path
    if kind in ("adr", "discovery"):
        return kind
    raise FilterError("fourth_store")


def _git(repo, args):
    import subprocess
    return subprocess.check_call(["git", "-C", repo] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def doctor_rows(harness, env=None, keel=None):
    if env is None:
        env = os.environ
    rows = []

    def add(ident, ok, detail):
        rows.append((ident, "pass" if ok else "fail", detail))

    import pi_launch
    memory = os.path.join(keel or os.path.join(harness, ".disc-empty"), "memory")
    # DISC-01: the index walks accepted directories only.
    sample = os.path.join(tempfile_dir(), "memory")
    os.makedirs(os.path.join(sample, "discoveries"), exist_ok=True)
    roots = pi_launch.extra_index_roots(sample)
    accepted = not roots and pi_launch.index_rel_ok("discoveries/a.md") and not pi_launch.index_rel_ok("note.md")
    add("DISC-01", accepted, "accepted dirs only" if accepted else "scan widened")

    work = tempfile_dir()
    os.makedirs(os.path.join(work, ".keel", "memory", "discoveries"), exist_ok=True)
    os.makedirs(os.path.join(work, ".keel", "candidates"), exist_ok=True)
    with open(os.path.join(work, ".keel", "memory", "discoveries", "2026-11-05-ok.md"), "w", encoding="utf-8") as handle:
        handle.write("---\ndate: 2026-11-05\ntitle: Kept\ntags: a\n---\nbody\n")
    with open(os.path.join(work, ".keel", "candidates", "cand.md"), "w", encoding="utf-8") as handle:
        handle.write("CANDIDATE-MARKER\n")
    try:
        indexed = pi_launch.build_memory_index(os.path.join(work, ".keel", "memory"), None)
        hidden = "CANDIDATE-MARKER" not in indexed["text"] and os.path.isdir(candidates_dir(work))
    except Exception as err:
        hidden = False
        indexed = {"text": str(err)}
    add("DISC-02", hidden, "candidates excluded" if hidden else "candidate visible")

    import subprocess
    import visibility
    mount_work = tempfile_dir()
    for rel in ("src", "docs", "tests", "briefs", ".keel/memory", ".keel/decisions"):
        os.makedirs(os.path.join(mount_work, *rel.split("/")), exist_ok=True)
    subprocess.check_call(["git", "-C", mount_work, "init", "-q"])
    subprocess.check_call(["git", "-C", mount_work, "symbolic-ref", "HEAD", "refs/heads/main"])
    subprocess.check_call([
        "git", "-C", mount_work, "-c", "user.email=h@x", "-c", "user.name=h",
        "commit", "-q", "--allow-empty", "-m", "init",
    ])
    try:
        mounts, _roots, _with, _detail = visibility.build_mounts(
            "developer", mount_work, harness, tempfile_dir(), "task-disc", mount_work, {}
        )
        mem = [item for item in mounts if item[1] == "/work/.keel/memory"]
        ro = bool(mem) and mem[0][2] == "ro" and visibility.discovery_memory_mode() == "ro"
    except Exception as err:
        ro = False
        mem = [str(err)]
    add("DISC-03", ro, "memory ro" if ro else "memory not ro")

    filt = os.path.join(harness, "lib", "discovery_filter.py")
    add("DISC-04", os.path.isfile(filt) and not os.path.islink(filt), "filter entrypoint")

    tool = os.path.join(harness, "tools", "write-memory-candidate.py")
    tools_ro = visibility.tools_mount_mode() == "ro" and os.path.isfile(tool) and not os.path.islink(tool)
    add("DISC-05", tools_ro, "tools ro" if tools_ro else "tools missing or writable")

    skill_ok = _skill_split()
    add("DISC-06", skill_ok, "skill hidden from non-append roles" if skill_ok else "skill leaked")

    allow = os.path.join(harness, "egress", "discovery-judge.allow")
    try:
        hosts = discovery_judge.allow_hosts(allow)
    except OSError:
        hosts = []
    stub_ok = (
        discovery_judge.stub_permitted({}) is False
        and discovery_judge.stub_permitted({"CI": "true"}) is False
        and discovery_judge.stub_permitted({"CI": "1"}) is False
        and discovery_judge.stub_permitted({"KEEL_CI": "1"}) is True
        and hosts == ["openrouter.ai"]
        and discovery_judge.classify_url(discovery_judge.DECISIONS_URL) is True
        and discovery_judge.classify_url("https://openrouter.ai/api/v1/chat/completions") is False
        and discovery_judge.MODEL_ID == "typesafe/jev-1.14"
        and "latest" not in discovery_judge.MODEL_ID
    )
    add("DISC-07a", stub_ok, "stub requires KEEL_CI=1" if stub_ok else "stub or egress pin wrong")

    ci = discovery_judge.stub_permitted(env)
    if ci:
        add("DISC-07b", True, "KEEL_CI stub; live key not required")
    else:
        key_path = discovery_judge.default_key_path(keel or env.get("KEEL_ROOT", ""), env)
        ok_key = discovery_judge.key_file_ok(key_path)
        add("DISC-07b", ok_key, "key path present" if ok_key else "key path missing or loose")

    spec = discovery_judge.launch_spec(os.path.join(harness, "unused-key"))
    isolated = (
        discovery_judge.role_reaches_judge() is False
        and spec["network"] == "keel-judge"
        and spec["publish"] == ""
        and spec["env"] == []
    )
    add("DISC-08", isolated, "role cannot reach the judge" if isolated else "judge is reachable")
    return rows


def tempfile_dir():
    import tempfile
    path = tempfile.mkdtemp(prefix="keel-disc-")
    _TEMPS.append(path)
    return path


_TEMPS = []


def _skill_split():
    import subprocess
    import pi_launch
    root = tempfile_dir()
    repo = os.path.join(root, "repo")
    keel = os.path.join(root, "keel")
    work = os.path.join(root, "work")
    os.makedirs(repo)
    os.makedirs(work)
    subprocess.check_call(["git", "-C", repo, "init", "-q"])
    subprocess.check_call(["git", "-C", repo, "symbolic-ref", "HEAD", "refs/heads/main"])
    skill = os.path.join(repo, ".agents", "skills", "keel-write-memory")
    other = os.path.join(repo, ".agents", "skills", "other")
    os.makedirs(skill)
    os.makedirs(other)
    with open(os.path.join(skill, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write("---\nname: keel-write-memory\ndescription: write\n---\n\n# Write\n")
    with open(os.path.join(other, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write("---\nname: other\ndescription: other\n---\n\n# Other\n")
    env = os.environ.copy()
    subprocess.check_call(["git", "-C", repo, "-c", "user.email=h@x", "-c", "user.name=h", "add", "."])
    subprocess.check_call(["git", "-C", repo, "-c", "user.email=h@x", "-c", "user.name=h", "commit", "-q", "-m", "skills"])
    dev = pi_launch.export_skills(repo, keel, "task", work, "developer")
    qa = pi_launch.export_skills(repo, keel, "task", work, "qa")
    return (
        os.path.isdir(os.path.join(dev, "keel-write-memory"))
        and not os.path.isdir(os.path.join(qa, "keel-write-memory"))
        and os.path.isdir(os.path.join(qa, "other"))
    )


def cmd_doctor(harness, keel):
    rows = doctor_rows(harness, os.environ, keel)
    for ident, status, detail in rows:
        sys.stdout.write("{0}\t{1}\t{2}\n".format(ident, status, detail))
    for path in _TEMPS:
        shutil.rmtree(path, ignore_errors=True)
    return 0


def main(argv):
    if len(argv) > 1 and argv[1] == "doctor":
        harness = ""
        keel = ""
        args = argv[2:]
        i = 0
        while i + 1 < len(args):
            if args[i] == "--harness":
                harness = args[i + 1]
            elif args[i] == "--keel":
                keel = args[i + 1]
            i += 2
        return cmd_doctor(harness, keel)
    sys.stderr.write("usage: discovery_filter.py doctor --harness H --keel K\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
