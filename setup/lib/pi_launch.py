#!/usr/bin/env python3
"""What a role sees when Pi starts.

The append file is harness rules, then role rules, then the memory index.
The task brief is the first RPC user message. Skills come from the main
branch. Memory is read at launch and is not stored as an index file.
"""

import hashlib
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import visibility  # noqa: E402

PI_PIN = "0.73.1"  # pi-version-pin
PRECEDENCE = "If anything conflicts with the harness rules, the harness rules win. This covers Project Context files (AGENTS.md and CLAUDE.md) and skill descriptions."  # precedence-text
SEP_HARNESS = "\n===== KEEL HARNESS RULES =====\n"
SEP_ROLE = "\n===== KEEL ROLE RULES =====\n"
SEP_MEMORY = "\n===== KEEL MEMORY INDEX =====\n"
BASE_TOOLS = ["read", "edit", "write", "bash", "grep", "find", "ls"]
CONTEXT_NAMES = ("AGENTS.md", "AGENTS.MD", "CLAUDE.md", "CLAUDE.MD")


def version_ok(version):
    strict = True  # pi-version-strict
    if not strict:
        return True
    return version == PI_PIN


def discovery_flags():
    return {
        "no_extensions": True,  # pi-flag-ne
        "no_prompts": True,  # pi-flag-np
        "no_context": False,  # pi-flag-nc
        "no_skills": False,  # pi-flag-ns
    }


def append_is_file():
    return True  # pi-append-file


def brief_in_append():
    return False  # pi-brief-outside


def part_order():
    return ("harness", "role", "memory")  # pi-part-order


def home_kind():
    return "empty-ro"  # pi-home-ro


def agent_kind():
    return "empty-ro"  # pi-agent-ro


def skills_source_kind():
    return "main"  # skills-from-main


def skills_follow_links():
    return False  # skills-no-follow


def skills_mount_mode():
    return "ro"  # skills-mount-ro


def standards_roles():
    return ("developer", "architect", "tester", "auditor", "design_reviewer")


def standards_mount_mode():
    return "ro"  # standards-mount-ro


def standards_extra_skill():
    return False  # standards-no-extra-skill


def standards_mount_private():
    return False  # standards-no-private-files


def _harness_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def install_standards_skill(dest, role):
    """Copy this role's generated standards view into its skills snapshot.

    Only keel-standards-<role> is added. The source, the generator, and the
    other roles' views stay out of the snapshot.
    """
    if role not in standards_roles():
        return
    view = os.path.join(_harness_root(), "standards", "views", role, "SKILL.md")
    if os.path.islink(view) or not os.path.isfile(view):
        return
    folder = os.path.join(dest, "keel-standards-" + role)
    os.makedirs(folder)
    with open(view, "rb") as incoming:
        data = incoming.read()
    with open(os.path.join(folder, "SKILL.md"), "wb") as outgoing:
        outgoing.write(data)
    if standards_extra_skill():
        for other in standards_roles():
            if other == role:
                continue
            extra = os.path.join(dest, "keel-standards-" + other)
            os.makedirs(extra, exist_ok=True)
            extra_file = os.path.join(extra, "SKILL.md")
            if not os.path.exists(extra_file):
                with open(extra_file, "w", encoding="utf-8") as handle:
                    handle.write("extra\n")
    if standards_mount_private():
        for leaf in ("rules.md", "gen.py", "roles.py"):
            with open(os.path.join(dest, leaf), "w", encoding="utf-8") as handle:
                handle.write("private\n")


def memory_mount_mode():
    return "ro"  # memory-mount-ro


def memory_sort_on():
    return True  # memory-sort


def memory_fence_on():
    return True  # memory-fence


def memory_mark_on():
    return True  # memory-superseded


def memory_fingerprint_on():
    return True  # memory-fingerprint


def memory_scan_root(configured):
    return configured  # memory-index-root


def extra_index_roots(memory_dir):
    return []  # disc-no-candidate-scan


def index_rel_ok(rel):
    rel = rel.replace(os.sep, "/")
    return rel.startswith("discoveries/") or rel.startswith("adr/")


def skill_visible_to(role):
    return role in ("developer", "orchestrator")


def arm_memory_audit(hook):
    sys.addaudithook(hook)  # memory-audit-hook
    return True


def tools_for(role):
    if role not in visibility.LAUNCHABLE:
        raise visibility.PolicyError("unknown_role", "role", 0, role)
    if role == "developer":
        extra = []  # developer-tools
        return list(BASE_TOOLS) + extra
    return list(BASE_TOOLS)


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def harness_rules(harness):
    path = os.path.join(harness, "pi", "harness-rules.md")
    text = _read(path).rstrip("\n")
    precedence = PRECEDENCE.strip()
    if precedence:
        return text + "\n" + precedence + "\n"
    return text + "\n"


def role_rules(harness, role):
    path = os.path.join(harness, "pi", "roles", role + ".md")
    if not os.path.isfile(path) or os.path.islink(path):
        raise visibility.PolicyError("role_rules_missing", path, 0, role)
    return _read(path)


def render_append(role, harness, index_text, brief):
    parts = {
        "harness": SEP_HARNESS + harness_rules(harness),
        "role": SEP_ROLE + role_rules(harness, role),
        "memory": SEP_MEMORY + index_text,
    }
    if brief_in_append():
        parts["memory"] += "\n" + brief
    text = ""
    for name in part_order():
        text += parts[name]
    return text


def build_argv(append_path, tools, append_text):
    flags = discovery_flags()
    argv = ["--mode", "rpc"]
    if flags["no_extensions"]:
        argv.append("-ne")
    if flags["no_prompts"]:
        argv.append("-np")
    if flags["no_context"]:
        argv.append("-nc")
    if flags["no_skills"]:
        argv.append("-ns")
    if append_is_file():
        argv.extend(["--append-system-prompt", append_path])
    else:
        argv.extend(["--append-system-prompt", append_text])
    argv.extend(["--tools", ",".join(tools)])
    return argv


def rpc_messages(brief):
    return [{"type": "prompt", "message": brief}]


def _reset_dir(path):
    if os.path.lexists(path):
        if os.path.islink(path) or not os.path.isdir(path):
            raise visibility.PolicyError("isolation_dir", path, 0, "")
        shutil.rmtree(path)
    os.makedirs(path)


def prepare_isolation(keel, task):
    base = os.path.join(keel, ".keel", "runs", task)
    os.makedirs(base, exist_ok=True)
    home = os.path.join(base, "pi-home")
    agent = os.path.join(base, "pi-agent")
    if home_kind() == "empty-ro":
        _reset_dir(home)
        home_mount = (home, "/pi-home", "ro")
    else:
        home_mount = ("/tmp", "/tmp", "rw")
    if agent_kind() == "empty-ro":
        _reset_dir(agent)
        agent_mount = (agent, "/pi-agent", "ro")
    else:
        _reset_dir(agent)
        ext = os.path.join(agent, "extensions")
        os.makedirs(ext)
        with open(os.path.join(ext, "seed.js"), "w", encoding="utf-8") as handle:
            handle.write("export default function () {}\n")
        agent_mount = (agent, "/pi-agent", "rw")
    return {
        "home": home,
        "agent": agent,
        "home_mount": home_mount,
        "agent_mount": agent_mount,
        "home_kind": home_kind(),
        "agent_kind": agent_kind(),
    }


def _sanitize(text):
    if not memory_fence_on():
        return text
    chars = []
    for char in text:
        code = ord(char)
        if code < 32 or code == 127:
            chars.append(" ")
        else:
            chars.append(char)
    cleaned = "".join(chars).replace("[/data]", "[data-end]")
    return cleaned


def _parse_header(text):
    date = ""
    title = ""
    tags = ""
    superseded = ""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        last = ""
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if ":" not in line:
                if last == "title":
                    title += "\n" + line
                continue
            key, val = line.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            last = key
            if key == "date":
                date = val
            elif key == "title":
                title = val
            elif key == "tags":
                tags = val
            elif key in ("superseded_by", "superseded-by"):
                superseded = val
    if date == "":
        date = "0000-00-00"
    return date, title, tags, superseded


def _under(path, root):
    path = os.path.abspath(os.fsdecode(path))
    root = os.path.abspath(root)
    return path == root or path.startswith(root + os.sep)


def _index_tree(scan, memory_dir, rows):
    for dirpath, dirnames, filenames in os.walk(scan, followlinks=False):
        kept = []
        for name in dirnames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                raise visibility.PolicyError("memory_symlink", path, 0, "")
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                raise visibility.PolicyError("memory_symlink", path, 0, "")
            if not os.path.isfile(path):
                continue
            if not _under(path, memory_dir) and os.path.abspath(path) != os.path.abspath(memory_dir):
                # Still open it so the audit hook records the widened scan.
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    handle.read(1)
                raise visibility.PolicyError("memory_path", path, 0, memory_dir)
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            rel = os.path.relpath(path, memory_dir).replace(os.sep, "/")
            if not index_rel_ok(rel):
                continue
            date, title, tags, superseded = _parse_header(text)
            rows.append({
                "date": date,
                "title": title,
                "tags": tags,
                "path": rel,
                "superseded_by": superseded,
            })


def build_memory_index(memory_dir, keel=None):
    """Read headers under memory_dir. Refuse a symlink. Log a fingerprint."""
    if os.path.islink(memory_dir) or not os.path.isdir(memory_dir):
        raise visibility.PolicyError("memory_missing", ".keel/memory", 0, memory_dir)
    opened = []

    def _hook(event, args):
        if event != "open" or not args:
            return
        path = args[0]
        if not isinstance(path, (str, bytes, os.PathLike)):
            return
        opened.append(os.fsdecode(path))

    armed = arm_memory_audit(_hook)
    start = len(opened)
    scan = memory_scan_root(memory_dir)
    walk_roots = [scan]
    for extra in extra_index_roots(memory_dir):
        if extra not in walk_roots:
            walk_roots.append(extra)
    rows = []
    for scan_root in walk_roots:
        if not os.path.isdir(scan_root) or os.path.islink(scan_root):
            if os.path.islink(scan_root):
                raise visibility.PolicyError("memory_symlink", scan_root, 0, "")
            continue
        _index_tree(scan_root, memory_dir, rows)
    scanned = opened[start:]
    for path in scanned:
        if not _under(path, memory_dir):
            raise visibility.PolicyError("memory_path", path, 0, memory_dir)
    rows.sort(key=lambda item: (item["date"], item["path"]), reverse=not memory_sort_on())
    blocks = []
    for item in rows:
        title = _sanitize(item["title"])
        tags = _sanitize(item["tags"])
        mark = "no"
        if item["superseded_by"] and memory_mark_on():
            mark = "SUPERSEDED"
        line = "date={0} title={1} tags={2} path={3} mark={4}".format(
            item["date"], title, tags, item["path"], mark
        )
        if memory_fence_on():
            blocks.append("[data]\n" + line + "\n[/data]")
        else:
            blocks.append(line)
    text = "\n".join(blocks)
    if text:
        text += "\n"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if keel and memory_fingerprint_on():
        log_dir = os.path.join(keel, ".keel", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "memory-index.log")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write("memory_index_sha256={0} count={1}\n".format(digest, len(rows)))
    return {
        "text": text,
        "sha256": digest,
        "count": len(rows),
        "audit_armed": bool(armed),
        "audit_fired": len(scanned),
        "opened": list(scanned),
    }


def _git(repo, args):
    return subprocess.check_output(["git", "-C", repo] + args)


def _copy_file(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(src, "rb") as handle:
        data = handle.read()
    with open(dest, "wb") as handle:
        handle.write(data)


def _export_tree(src, dest, follow):
    if not os.path.isdir(src):
        return
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        rel = os.path.relpath(dirpath, src)
        for name in list(dirnames):
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                if not follow:
                    raise visibility.PolicyError("skills_symlink", path, 0, "")
                dirnames.remove(name)
        for name in filenames:
            path = os.path.join(dirpath, name)
            inner = name if rel == "." else os.path.join(rel, name)
            target = os.path.join(dest, inner)
            if os.path.islink(path):
                if not follow:
                    raise visibility.PolicyError("skills_symlink", path, 0, "")
                real = os.path.realpath(path)
                if os.path.isfile(real):
                    _copy_file(real, target)
                continue
            if os.path.isfile(path):
                _copy_file(path, target)


def _export_git(repo, dest, follow):
    raw = _git(repo, ["ls-tree", "-r", "-z", "main", "--", ".agents/skills"])
    prefix = ".agents/skills/"
    for rec in raw.split(b"\0"):
        if not rec or b"\t" not in rec:
            continue
        meta, path_b = rec.split(b"\t", 1)
        parts = meta.split()
        mode = parts[0].decode("ascii")
        sha = parts[2].decode("ascii")
        rel = path_b.decode("utf-8")
        if not rel.startswith(prefix):
            continue
        inner = rel[len(prefix):]
        if inner == "":
            continue
        target = os.path.join(dest, *inner.split("/"))
        if mode == "120000":
            if not follow:
                raise visibility.PolicyError("skills_symlink", rel, 0, "")
            link = _git(repo, ["cat-file", "blob", sha]).decode("utf-8")
            link = link.rstrip("\n")
            base = os.path.join(repo, os.path.dirname(rel))
            real = link if os.path.isabs(link) else os.path.normpath(os.path.join(base, link))
            if os.path.isfile(real) and not os.path.islink(real):
                _copy_file(real, target)
            continue
        if mode not in ("100644", "100755"):
            raise visibility.PolicyError("skills_export", rel, 0, mode)
        blob = _git(repo, ["cat-file", "blob", sha])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(blob)


def export_skills(repo, keel, task, work, role=None):
    label = "skills-main" if role is None else "skills-main-" + role
    dest = os.path.join(keel, ".keel", "runs", task, label)
    if os.path.lexists(dest):
        if os.path.islink(dest):
            raise visibility.PolicyError("skills_symlink", dest, 0, "")
        shutil.rmtree(dest)
    os.makedirs(dest)
    follow = skills_follow_links()
    if skills_source_kind() == "worktree":
        _export_tree(os.path.join(work, ".agents", "skills"), dest, follow)
    else:
        _export_git(repo, dest, follow)
    _hide_memory_skill(dest, role)
    install_standards_skill(dest, role)
    return dest


def _hide_memory_skill(dest, role):
    if skill_visible_to(role):
        return
    path = os.path.join(dest, "keel-write-memory")
    if os.path.islink(path):
        raise visibility.PolicyError("skills_symlink", path, 0, "")
    if os.path.isdir(path):
        shutil.rmtree(path)


def export_tools(harness, keel, task):
    src = os.path.join(harness, "tools")
    dest = os.path.join(keel, ".keel", "runs", task, "tools")
    if os.path.lexists(dest):
        if os.path.islink(dest):
            raise visibility.PolicyError("tools_symlink", dest, 0, "")
        shutil.rmtree(dest)
    if not os.path.isdir(src) or os.path.islink(src):
        raise visibility.PolicyError("tools_missing", src, 0, "")
    os.makedirs(dest)
    for name in os.listdir(src):
        path = os.path.join(src, name)
        if os.path.islink(path):
            raise visibility.PolicyError("tools_symlink", path, 0, "")
        if os.path.isfile(path):
            _copy_file(path, os.path.join(dest, name))
    return dest


def _ensure_fixture(work, repo):
    os.makedirs(os.path.join(work, ".keel", "memory"), exist_ok=True)
    if os.path.isdir(os.path.join(repo, ".git")):
        return
    os.makedirs(repo, exist_ok=True)
    subprocess.check_call(["git", "-C", repo, "init", "-q"])
    subprocess.check_call(["git", "-C", repo, "symbolic-ref", "HEAD", "refs/heads/main"])
    subprocess.check_call([
        "git", "-C", repo, "-c", "user.email=h@x", "-c", "user.name=h",
        "commit", "-q", "--allow-empty", "-m", "init",
    ])


def prepare_launch(role, brief, work, harness, keel, task, repo):
    memory_dir = os.path.join(work, ".keel", "memory")
    index = build_memory_index(memory_dir, keel)
    text = render_append(role, harness, index["text"], brief)
    runs = os.path.join(keel, ".keel", "runs", task)
    os.makedirs(runs, exist_ok=True)
    append_path = os.path.join(runs, "append-" + role + ".md")
    with open(append_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    argv = build_argv(append_path, tools_for(role), text)
    iso = prepare_isolation(keel, task)
    return {
        "argv": argv,
        "append_path": append_path,
        "append_text": text,
        "rpc": rpc_messages(brief),
        "index": index,
        "isolation": iso,
        "tools": tools_for(role),
    }


def _docker():
    return os.environ.get("DOCKER", "docker").split()


def _run(cmd, timeout=60):
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except OSError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def installed_version():
    code = (
        "import { pathToFileURL } from 'node:url';"
        "import { delimiter, join } from 'node:path';"
        "import { existsSync } from 'node:fs';"
        "const roots = (process.env.NODE_PATH || '').split(delimiter).filter(Boolean);"
        "let root = '';"
        "for (const item of roots) {"
        "  const candidate = join(item, '@mariozechner', 'pi-coding-agent');"
        "  if (existsSync(join(candidate, 'package.json'))) { root = candidate; break; }"
        "}"
        "if (!root) { process.stderr.write('pi package not found'); process.exit(1); }"
        "const mod = await import(pathToFileURL(join(root, 'dist/index.js')).href);"
        "process.stdout.write(mod.VERSION);"
    )
    rc, out, err = _run(["node", "--input-type=module", "-e", code], timeout=30)
    if rc != 0:
        raise visibility.PolicyError("pi_version", "node", 0, err.strip().splitlines()[-1] if err.strip() else "node")
    return out.strip()


def image_pi_version():
    rc, out, err = _run(_docker() + ["run", "--rm", "--network", "none", "keel-pi", "pi", "--version"], timeout=60)
    text = out.strip() or err.strip()
    if rc != 0 or text == "":
        detail = text.splitlines()[-1] if text else "image"
        raise visibility.PolicyError("pi_version", "keel-pi", 0, detail)
    return text.splitlines()[-1].strip()


def ancestor_script(harness):
    return os.path.join(harness, "docker", "ancestor-guard.sh")


def image_ancestors_clean(harness):
    script = ancestor_script(harness)
    if not os.path.isfile(script):
        return False, "guard missing"
    cmd = _docker() + [
        "run", "--rm", "--network", "none",
        "-v", script + ":/keel-ancestor-guard.sh:ro",
        "keel-git", "sh", "/keel-ancestor-guard.sh", "/",
    ]
    rc, out, err = _run(cmd, timeout=60)
    if rc != 0:
        return False, (err or out).strip() or "guard failed"
    return True, "no context file above /work"


def _dir_empty(path):
    if os.path.islink(path) or not os.path.isdir(path):
        return False
    return os.listdir(path) == []


def _no_symlinks(root):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in list(dirnames) + list(filenames):
            if os.path.islink(os.path.join(dirpath, name)):
                return False
    return True


def pi_rows(harness, keel, work, repo, task):
    """Return PI-01..PI-09 as (id, status, detail). status is pass or fail."""
    _ensure_fixture(work, repo)
    rows = []
    try:
        host_ver = installed_version()
        image_ver = image_pi_version()
        if version_ok(host_ver) and version_ok(image_ver):
            rows.append(("PI-01", "pass", host_ver))
        else:
            rows.append(("PI-01", "fail", host_ver + " image " + image_ver))
    except visibility.PolicyError as err:
        rows.append(("PI-01", "fail", err.code))

    try:
        launch = prepare_launch("developer", "brief", work, harness, keel, task, repo)
    except visibility.PolicyError as err:
        for ident in ("PI-02", "PI-03", "PI-04", "PI-05", "PI-06", "PI-08"):
            rows.append((ident, "fail", err.code))
        launch = None

    if launch is not None:
        argv = launch["argv"]
        path = ""
        if "--append-system-prompt" in argv:
            idx = argv.index("--append-system-prompt")
            if idx + 1 < len(argv):
                path = argv[idx + 1]
        runs = os.path.join(keel, ".keel", "runs")
        if path and os.path.isfile(path) and not os.path.islink(path) and _under(path, runs):
            rows.append(("PI-02", "pass", "append file"))
        else:
            rows.append(("PI-02", "fail", "append is not a file under .keel/runs"))
        flags = discovery_flags()
        ok_flags = (
            flags["no_extensions"] and "-ne" in argv
            and flags["no_prompts"] and "-np" in argv
            and not flags["no_context"] and "-nc" not in argv
            and not flags["no_skills"] and "-ns" not in argv
            and "-e" not in argv
        )
        rows.append(("PI-03", "pass" if ok_flags else "fail", "flags"))
        iso = launch["isolation"]
        home_ok = iso["home_kind"] == "empty-ro" and _dir_empty(iso["home"]) and iso["home_mount"][2] == "ro"
        rows.append(("PI-05", "pass" if home_ok else "fail", iso["home_kind"]))
        agent_ok = iso["agent_kind"] == "empty-ro" and _dir_empty(iso["agent"]) and iso["agent_mount"][2] == "ro"
        rows.append(("PI-04", "pass" if agent_ok else "fail", iso["agent_kind"]))
        try:
            host = export_skills(repo, keel, task, work)
            mode = skills_mount_mode()
            skills_ok = (
                skills_source_kind() == "main"
                and mode == "ro"
                and os.path.isdir(host)
                and not os.path.islink(host)
                and _under(host, os.path.join(keel, ".keel", "runs"))
                and _no_symlinks(host)
                and os.path.basename(os.path.dirname(host)) != "work"
            )
            # Host path must not be the worktree skills directory.
            work_skills = os.path.abspath(os.path.join(work, ".agents", "skills"))
            if os.path.abspath(host) == work_skills:
                skills_ok = False
            rows.append(("PI-06", "pass" if skills_ok else "fail", mode))
        except visibility.PolicyError as err:
            rows.append(("PI-06", "fail", err.code))
        text = launch["append_text"]
        prec_ok = PRECEDENCE != "" and PRECEDENCE in text and "Project Context" in PRECEDENCE and "skill descriptions" in PRECEDENCE
        rows.append(("PI-08", "pass" if prec_ok else "fail", "precedence"))

    clean, detail = image_ancestors_clean(harness)
    rows.append(("PI-07", "pass" if clean else "fail", detail))
    rows.append(("PI-09", "pass", "N/A"))
    order = ["PI-0{0}".format(n) for n in range(1, 10)]
    by_id = {item[0]: item for item in rows}
    return [by_id[ident] for ident in order if ident in by_id]


def cmd_doctor(args):
    rows = pi_rows(args.harness, args.keel, args.work, args.repo, args.task)
    for ident, status, detail in rows:
        sys.stdout.write("{0}\t{1}\t{2}\n".format(ident, status, detail))
    return 0 if all(status == "pass" for _ident, status, _detail in rows) else 1


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: pi_launch.py doctor --harness H --keel K --work W --repo R --task T\n")
        return 2
    if argv[1] == "doctor":
        return cmd_doctor(_parse(argv[2:]))
    sys.stderr.write("unknown command\n")
    return 2


def _parse(argv):
    class Args(object):
        pass
    out = Args()
    out.harness = ""
    out.keel = ""
    out.work = ""
    out.repo = ""
    out.task = "task-1"
    i = 0
    while i < len(argv):
        key = argv[i]
        if i + 1 >= len(argv):
            break
        val = argv[i + 1]
        if key == "--harness":
            out.harness = val
        elif key == "--keel":
            out.keel = val
        elif key == "--work":
            out.work = val
        elif key == "--repo":
            out.repo = val
        elif key == "--task":
            out.task = val
        i += 2
    return out


if __name__ == "__main__":
    sys.exit(main(sys.argv))
