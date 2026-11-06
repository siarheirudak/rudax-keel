#!/usr/bin/env python3
"""Step 6 standards generator checks. Green results use BLOCKED."""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
REPO = os.path.dirname(SETUP)
sys.path.insert(0, os.path.join(SETUP, "lib"))
sys.path.insert(0, HERE)

import pi_launch  # noqa: E402
import step4_check  # noqa: E402
import visibility  # noqa: E402


def _load_gen():
    path = os.path.join(SETUP, "standards", "gen.py")
    spec = importlib.util.spec_from_file_location("standards_gen", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = _load_gen()

RULES = os.path.join(SETUP, "standards", "rules.md")
VIEWS = os.path.join(SETUP, "standards", "views")
FIXTURE = os.path.join(HERE, "fixtures", "step6", "rules.md")
GOLDEN = os.path.join(HERE, "fixtures", "step6", "golden")
ROLES_PY = os.path.join(SETUP, "standards", "roles.py")

DEVELOPER = {
    "DES-01", "DES-03", "DES-04", "DES-05",
    "CMP-01",
    "REA-01", "REA-02", "REA-04",
    "TST-01", "TST-02", "TST-03",
    "COR-01", "COR-02", "COR-03", "COR-04", "COR-05",
    "ERR-01", "ERR-02", "ERR-04",
    "TYP-02", "TYP-03",
    "SEC-01", "SEC-02", "SEC-03", "SEC-04", "SEC-05", "SEC-06", "SEC-07", "SEC-09",
    "SCO-01", "SCO-02",
    "REL-01", "REL-02",
    "DOC-01", "DOC-02",
    "DAT-01", "API-01", "RES-01",
}
ARCHITECT = {
    "DES-01", "DES-03", "DES-04", "DES-05",
    "COR-03", "COR-05",
    "TYP-03",
    "SEC-01", "SEC-06", "SEC-09",
    "SCO-01", "SCO-02",
    "REL-01", "REL-02",
    "DOC-02",
    "DAT-01", "API-01", "RES-01",
}
TESTER = {
    "TST-01", "TST-02", "TST-03",
    "COR-01", "COR-02", "COR-03", "COR-04", "COR-05",
    "ERR-01", "ERR-02",
    "DAT-01", "API-01", "RES-01",
    "SEC-01", "SEC-02", "SEC-03", "SEC-05", "SEC-07", "SEC-09",
}
AUDITOR = {
    "DES-01",
    "COR-01", "COR-02", "COR-03", "COR-04", "COR-05",
    "TST-01", "TST-02",
    "ERR-01", "ERR-02", "ERR-04",
    "TYP-02", "TYP-03",
    "SEC-01", "SEC-02", "SEC-03", "SEC-04", "SEC-05", "SEC-06", "SEC-07", "SEC-09",
    "SCO-01", "SCO-02",
    "REL-01", "REL-02",
    "DOC-01", "DOC-02",
    "DAT-01", "API-01", "RES-01",
}
DESIGN = {"DES-01", "DES-03", "DES-04", "DES-05", "API-01"}
GATE = {
    "STY-01", "STY-02", "STY-04",
    "REA-03",
    "TYP-01", "TYP-02",
    "DUP-01", "CX-01",
    "ERR-03", "SEC-03",
}
EXPECTED = {
    "developer": DEVELOPER,
    "architect": ARCHITECT,
    "tester": TESTER,
    "auditor": AUDITOR,
    "design_reviewer": DESIGN,
    "static_gate": GATE,
}
REVIEWERS = ("architect", "auditor", "design_reviewer")
MODEL_ROLES = ("developer", "architect", "tester", "auditor", "design_reviewer")
AUTHOR_ONLY = {"REA-01", "REA-02", "REA-04", "CMP-01"}
GATE_ONLY = {"STY-01", "STY-02", "STY-04", "REA-03", "TYP-01", "DUP-01", "CX-01", "ERR-03"}
RETIRED = {"DES-02", "CMP-03", "TST-04", "CMP-02", "CMP-04", "STY-03"}
HEADING_RE = re.compile(r"^### ([A-Z0-9-]+) —", re.M)
PRIVATE_NAMES = {"rules.md", "gen.py", "roles.py"}


def say(ident, status, detail):
    print("RESULT {0}: {1} ({2})".format(ident, status, detail))
    return status in ("BLOCKED", "CONTAINED", "PARTIAL", "N/A")


def load_real():
    return gen.load(RULES)


def headings(text):
    return HEADING_RE.findall(text)


def section(text, ident):
    marker = "### " + ident + " —"
    start = text.find(marker)
    if start < 0:
        return ""
    nxt = text.find("\n### ", start + 1)
    if nxt < 0:
        return text[start:]
    return text[start:nxt]


def rendered():
    model, data = load_real()
    return model, gen.render_views(model, data)


def base_rule(ident="DES-01", extra="", kind="judgment", severity="advice", authors="developer", reviewers="auditor"):
    lines = [
        "### {0} — Example".format(ident),
        "```keys",
        "kind: " + kind,
        "severity: " + severity,
        "authors: " + authors,
    ]
    if reviewers is not None:
        lines.append("reviewers: " + reviewers)
    lines.extend([
        "rule: Do the thing.",
        "flag: It breaks the contract.",
        "noflag: It matches the contract.",
        "source: Fixture source",
    ])
    if extra:
        lines.append(extra)
    lines.append("```")
    return "\n".join(lines) + "\n"


def document(body):
    return "## Rules\n\n" + body


def rejected(text):
    try:
        gen.parse(text, "fixture.md")
    except gen.StandardsError as err:
        return err
    return None


def line_of(text, marker):
    for number, line in enumerate(text.splitlines(), 1):
        if marker in line:
            return number
    return None


def check_h1():
    data = open(FIXTURE, "rb").read()
    model = gen.parse(data.decode("utf-8"), FIXTURE)
    views = gen.render_views(model, data)
    bad = []
    for role, text in views.items():
        path = os.path.join(GOLDEN, role, "SKILL.md")
        golden = open(path, "rb").read()
        if text.encode("utf-8") != golden:
            bad.append(role)
    if bad:
        return say("S6-H1", "NOT BLOCKED", ",".join(bad))
    return say("S6-H1", "BLOCKED", "fixture matches golden")


def _seed_view(seed, role):
    code = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import gen\n"
        "data = open(sys.argv[2], 'rb').read()\n"
        "model = gen.parse(data.decode('utf-8'), sys.argv[2])\n"
        "views = gen.render_views(model, data)\n"
        "sys.stdout.buffer.write(views[sys.argv[3]].encode('utf-8'))\n"
    )
    env = {
        "PYTHONHASHSEED": str(seed),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": os.environ.get("PATH", ""),
    }
    proc = subprocess.run(
        [sys.executable, "-c", code, os.path.join(SETUP, "standards"), FIXTURE, role],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:200])
    return proc.stdout


def check_h2():
    bad = []
    for role in EXPECTED:
        golden = open(os.path.join(GOLDEN, role, "SKILL.md"), "rb").read()
        first = _seed_view(1, role)
        second = _seed_view(2, role)
        if first != golden or second != golden or first != second:
            bad.append(role)
    if bad:
        return say("S6-H2", "NOT BLOCKED", ",".join(bad))
    return say("S6-H2", "BLOCKED", "same bytes across hash seeds")


def check_h3():
    model, data = load_real()
    code, message = gen.audit(model, data, VIEWS)
    source = open(RULES, encoding="utf-8").read()
    recorded = (
        "Suppression syntax is not accepted." in source
        and "owner-controlled approval path" in source
        and "owner-controlled approval path" in gen.REVIEW_PRECONDITION
    )
    if code == 0 and message == "" and recorded:
        return say("S6-H3", "BLOCKED", "clean tree and suppression precondition")
    return say("S6-H3", "NOT BLOCKED", "code {0}".format(code))


def check_h4():
    model, views = rendered()
    bad = []
    for role, expect in EXPECTED.items():
        got = set(gen.ids_for(role, model))
        heads = set(headings(views[role]))
        if got != expect or heads != expect:
            bad.append(role)
    if bad:
        return say("S6-H4", "NOT BLOCKED", ",".join(bad))
    return say("S6-H4", "BLOCKED", "membership matches the source lists")


def check_h5():
    model, _views = rendered()
    dev = set(gen.ids_for("developer", model))
    bad = []
    if not AUTHOR_ONLY <= dev:
        bad.append("developer")
    for role in REVIEWERS:
        leaked = set(gen.ids_for(role, model)) & AUTHOR_ONLY
        if leaked:
            bad.append(role)
    if bad:
        return say("S6-H5", "NOT BLOCKED", ",".join(bad))
    return say("S6-H5", "BLOCKED", "author-only ids stay with the developer")


def check_h6():
    model, views = rendered()
    bad = []
    for role in EXPECTED:
        found = set(gen.ids_for(role, model)) | set(headings(views[role]))
        if found & RETIRED:
            bad.append(role)
    dev = views["developer"]
    gate = views["static_gate"]
    auditor = views["auditor"]
    if "one obvious place for a concern" not in dev or "speculative generality" not in dev:
        bad.append("des-content")
    if "clause: speculative generality: advice" not in section(dev, "DES-01"):
        bad.append("cmp02-advice")
    if "configured complexity budget" not in gate:
        bad.append("cx")
    if "greenwash" not in auditor or "expected-fail" not in auditor:
        bad.append("cor04")
    if "nesting" not in dev:
        bad.append("cmp01")
    if "line length" not in gate or "quote" not in gate:
        bad.append("sty")
    if bad:
        return say("S6-H6", "NOT BLOCKED", ",".join(bad))
    return say("S6-H6", "BLOCKED", "merges applied")


def _expect_severity(rule, role):
    if role in rule.reviewers and rule.block_reviewers and role not in rule.block_reviewers:
        return "advice", None
    bar = rule.block_when.get("bar") if rule.block_when else None
    return rule.severity, bar


def check_h7():
    model, views = rendered()
    bad = []
    for rule in model.rules:
        if rule.kind == "mechanical":
            continue
        for role in ("developer", "auditor", "architect", "design_reviewer"):
            if rule.id not in gen.ids_for(role, model):
                continue
            body = section(views[role], rule.id)
            if "Flag: " not in body or "Do not flag: " not in body:
                bad.append(role + ":" + rule.id + ":examples")
                continue
            severity, bar = _expect_severity(rule, role)
            if "severity: " + severity not in body:
                bad.append(role + ":" + rule.id + ":severity")
            if bar and "bar: " + bar not in body:
                bad.append(role + ":" + rule.id + ":bar")
    if bad:
        return say("S6-H7", "NOT BLOCKED", bad[0])
    return say("S6-H7", "BLOCKED", "examples, severity, and bars survive")


def _snapshot_problems(dest, role):
    problems = []
    own = None
    if role in pi_launch.standards_roles():
        own = "keel-standards-" + role
        if not os.path.isdir(os.path.join(dest, own)):
            problems.append("missing-own")
    for dirpath, dirnames, filenames in os.walk(dest):
        for name in list(dirnames) + list(filenames):
            if name.startswith("keel-standards-") and name != own:
                problems.append(name)
            if name in PRIVATE_NAMES:
                problems.append(name)
            if name == "keel-standards-static_gate":
                problems.append(name)
    return problems


def _role_write(mounts):
    """Try a write on the skills mount inside a container using the role mounts.

    A pass is only a read-only rejection. Any other docker result is a failure.
    """
    skills = [item for item in mounts if item[1] == "/work/.agents/skills"]
    if len(skills) != 1:
        return False, "skills mount missing"
    host, dest, mode = skills[0]
    if mode != "ro":
        return False, "mode " + mode
    docker = step4_check.docker_bin()
    if shutil.which(docker[0]) is None:
        return False, "docker missing"
    script = (
        "if echo probe > '{0}/pwn'; then echo WROTE; else echo DENIED; fi"
    ).format(dest)
    cmd = docker + [
        "run", "--rm", "--network", "none",
        "--user", "{0}:{1}".format(os.getuid(), os.getgid()),
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m",
    ]
    for item_host, item_dest, item_mode in mounts:
        cmd.extend(["-v", "{0}:{1}:{2}".format(item_host, item_dest, item_mode)])
    cmd.extend(["-w", "/work", "keel-git", "sh", "-c", script])
    proc = step4_check.run(cmd, timeout=60)
    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    landed = os.path.lexists(os.path.join(host, "pwn"))
    if "WROTE" in out or landed:
        return False, "wrote"
    if proc.returncode != 0 and "Read-only file system" not in out:
        tail = " ".join(out.split())[:120] or "docker failed"
        return False, tail
    if "DENIED" in out and "Read-only file system" in out and not landed:
        return True, "read-only"
    return False, "unexpected"


def check_h8():
    root = tempfile.mkdtemp(prefix="s6-h8-")
    try:
        repo, work, keel = step4_check.make_tree(root)
        rows = []
        bad = False
        for role in visibility.LAUNCHABLE:
            dest = pi_launch.export_skills(repo, keel, "h8-" + role, work, role)
            problems = _snapshot_problems(dest, role)
            mounts, _r, _w, _d = step4_check.mounts_for(role, repo, work, keel)
            item = step4_check.mount_named(mounts, "/work/.agents/skills")
            if item is None:
                problems.append("mount missing")
            elif role in pi_launch.standards_roles():
                held, detail = _role_write(mounts)
                if held:
                    rows.append(role + ": " + detail)
                else:
                    problems.append(detail)
            if problems:
                bad = True
                rows.append(role + ": " + ",".join(problems))
        detail = "; ".join(rows)
        if bad:
            return say("S6-H8", "NOT BLOCKED", detail)
        return say("S6-H8", "BLOCKED", detail)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_h9():
    model, views = rendered()
    auditor_ids = set(gen.ids_for("auditor", model))
    tester_ids = set(gen.ids_for("tester", model))
    if "TST-02" in auditor_ids and "TST-02" in tester_ids and "TST-02" in headings(views["tester"]):
        return say("S6-H9", "BLOCKED", "auditor cites TST-02 and tester authors it")
    return say("S6-H9", "NOT BLOCKED", "TST-02")


def check_h10():
    model, _views = rendered()
    wanted = {
        "DAT-01": {"developer", "architect", "tester", "auditor"},
        "RES-01": {"developer", "architect", "tester", "auditor"},
        "SEC-09": {"developer", "architect", "tester", "auditor"},
        "API-01": {"developer", "architect", "tester", "auditor", "design_reviewer"},
    }
    bad = []
    for ident, owners in wanted.items():
        for role in EXPECTED:
            present = ident in gen.ids_for(role, model)
            if present != (role in owners):
                bad.append(role + ":" + ident)
    if bad:
        return say("S6-H10", "NOT BLOCKED", ",".join(bad))
    return say("S6-H10", "BLOCKED", "new ids match the role lists")


def check_h11():
    _model, views = rendered()
    bad = []
    for role in MODEL_ROLES:
        if "recognizable secret literals" in views[role]:
            bad.append(role)
    gate = views["static_gate"]
    auditor = section(views["auditor"], "SEC-03")
    if "recognizable secret literals" not in gate:
        bad.append("gate-scanner")
    if "client-visible payloads" in gate or "Flag:" in section(gate, "SEC-03"):
        bad.append("gate-semantic")
    if "client-visible payloads" not in auditor:
        bad.append("auditor-semantic")
    if bad:
        return say("S6-H11", "NOT BLOCKED", ",".join(bad))
    return say("S6-H11", "BLOCKED", "SEC-03 facets stay split")


def check_h12():
    model, _views = rendered()
    banned = AUTHOR_ONLY | GATE_ONLY
    bad = []
    for role in REVIEWERS:
        leaked = set(gen.ids_for(role, model)) & banned
        if leaked:
            bad.append(role)
    if bad:
        return say("S6-H12", "NOT BLOCKED", ",".join(bad))
    return say("S6-H12", "BLOCKED", "reviewer ids exclude author-only and gate-only")


def check_h13():
    _model, views = rendered()
    body = section(views["design_reviewer"], "DES-01")
    ok = (
        "system complexity" in body
        and "simple over clever" in body
        and "clause: simple over clever: advice" in body
        and "clause: system complexity: advice" in body
        and "clause: speculative generality: advice" in body
    )
    if ok:
        return say("S6-H13", "BLOCKED", "DES-01 advice clauses")
    return say("S6-H13", "NOT BLOCKED", "DES-01 clauses")


def check_h14():
    model, views = rendered()
    if "COR-05" in gen.ids_for("architect", model) and "COR-05" in headings(views["architect"]):
        return say("S6-H14", "BLOCKED", "architect includes COR-05")
    return say("S6-H14", "NOT BLOCKED", "COR-05")


def check_h15():
    _model, views = rendered()
    auditor = section(views["auditor"], "API-01")
    design = section(views["design_reviewer"], "API-01")
    ok = (
        "severity: block" in auditor
        and "bar: demonstrated" in auditor
        and "severity: advice" in design
        and "bar:" not in design
    )
    if ok:
        return say("S6-H15", "BLOCKED", "API-01 block for auditor, advice for design reviewer")
    return say("S6-H15", "NOT BLOCKED", "API-01 severity")


def check_a1():
    root = tempfile.mkdtemp(prefix="s6-a1-")
    try:
        copied = os.path.join(root, "views")
        shutil.copytree(VIEWS, copied)
        path = os.path.join(copied, "developer", "SKILL.md")
        text = open(path, encoding="utf-8").read().replace("severity:", "severity-edited:", 1)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        model, data = load_real()
        code, message = gen.audit(model, data, copied)
        if code == 1 and message:
            return say("S6-A1", "BLOCKED", "hand-edited view fails the drift check")
        return say("S6-A1", "NOT BLOCKED", "code {0}".format(code))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_a2():
    root = tempfile.mkdtemp(prefix="s6-a2-")
    try:
        copied = os.path.join(root, "views")
        shutil.copytree(VIEWS, copied)
        extra = os.path.join(copied, "developer", "extra.md")
        with open(extra, "w", encoding="utf-8") as handle:
            handle.write("extra\n")
        model, data = load_real()
        code, message = gen.audit(model, data, copied)
        if code == 1 and "extra file:" in message:
            return say("S6-A2", "BLOCKED", "extra file fails the drift check")
        return say("S6-A2", "NOT BLOCKED", "code {0}".format(code))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _must_reject(text, marker, message_part):
    err = rejected(text)
    number = line_of(text, marker)
    if err is None:
        return False
    if number is not None and err.line != number:
        return False
    if message_part not in err.message:
        return False
    return True


def check_a3():
    text = document(base_rule("SEC-08"))
    if _must_reject(text, "### SEC-08", "policy id"):
        return say("S6-A3", "BLOCKED", "SEC-08 heading rejected")
    return say("S6-A3", "NOT BLOCKED", "SEC-08 accepted")


def check_a4():
    model, views = rendered()
    bad = []
    for role in EXPECTED:
        if "SEC-08" in gen.ids_for(role, model) or "SEC-08" in headings(views[role]):
            bad.append(role)
    if bad:
        return say("S6-A4", "NOT BLOCKED", ",".join(bad))
    return say("S6-A4", "BLOCKED", "SEC-08 is not an emittable id")


def check_a5():
    text = document(
        "### DES-01 — Example\n"
        "```keys\n"
        "kind: judgment\n"
        "severity: advice\n"
        "authors: developer\n"
        "reviewers: auditor\n"
        "rule: Do the thing.\n"
        "noflag: It matches the contract.\n"
        "source: Fixture source\n"
        "```\n"
    )
    if _must_reject(text, "### DES-01", "flag"):
        return say("S6-A5", "BLOCKED", "missing example rejected")
    return say("S6-A5", "NOT BLOCKED", "missing example accepted")


def check_a6():
    text = document(base_rule("DES-01", extra="merges: DES-02") + "\n" + base_rule("DES-02"))
    if _must_reject(text, "### DES-01 — Example", "merged id"):
        return say("S6-A6", "BLOCKED", "redeclared merge rejected")
    return say("S6-A6", "NOT BLOCKED", "redeclared merge accepted")


def check_a7():
    cases = []
    unknown = document(base_rule("DES-01", extra="frob: no"))
    cases.append((unknown, "frob:", "unknown key"))
    duplicate = document(base_rule("DES-01") + "\n" + base_rule("DES-01", extra=""))
    cases.append((duplicate, "### DES-01 — Example\n```keys\nkind: judgment\nseverity: advice\nauthors: developer\nreviewers: auditor\nrule: Do the thing.\nflag: It breaks the contract.\nnoflag: It matches the contract.\nsource: Fixture source\n```\n\n### DES-01", "duplicate id"))
    bad_id = document(base_rule("NOPE"))
    cases.append((bad_id, "### NOPE", "bad id"))
    family = document(base_rule("XYZ-01"))
    cases.append((family, "### XYZ-01", "unknown family"))
    suppress = document(base_rule("DES-01", extra="suppress: COR-04"))
    cases.append((suppress, "suppress:", "suppression"))
    noqa = "## Rules\n\n# noqa\n\n" + base_rule("DES-01")
    cases.append((noqa, "# noqa", "suppression"))
    bad = []
    for text, marker, part in cases:
        # The duplicate fixture's marker must be the second heading.
        if part == "duplicate id":
            first = text.find("### DES-01")
            second = text.find("### DES-01", first + 1)
            err = rejected(text)
            if err is None or "duplicate id" not in err.message:
                bad.append(part)
                continue
            line = text[:second].count("\n") + 1
            if err.line != line:
                bad.append("duplicate-line")
            continue
        if not _must_reject(text, marker, part):
            bad.append(part)
    if bad:
        return say("S6-A7", "NOT BLOCKED", ",".join(bad))
    return say("S6-A7", "BLOCKED", "strict parser names the line")


def check_a8():
    text = (
        "## Rules\n\n"
        "### DES-01 — Example\n"
        "```keys\n"
        "kind: judgment\n"
        "severity: advice\n"
        "authors: developer\n"
        "reviewers: auditor\n"
        "rule: Do the thing.\n"
        "flag: It breaks the contract.\n"
        "noflag: It matches the contract.\n"
        "```\n"
    )
    if _must_reject(text, "### DES-01", "source"):
        return say("S6-A8", "BLOCKED", "missing source rejected")
    return say("S6-A8", "NOT BLOCKED", "missing source accepted")


def check_a9():
    root = tempfile.mkdtemp(prefix="s6-a9-")
    try:
        repo, work, keel = step4_check.make_tree(root)
        bad = []
        for role in visibility.LAUNCHABLE:
            dest = pi_launch.export_skills(repo, keel, "a9-" + role, work, role)
            problems = _snapshot_problems(dest, role)
            if problems:
                bad.append(role)
        if bad:
            return say("S6-A9", "NOT BLOCKED", ",".join(bad))
        return say("S6-A9", "BLOCKED", "snapshot excludes other views and the source")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_a10():
    text = document(base_rule("DES-01", authors="developer, nobody"))
    if _must_reject(text, "### DES-01", "unknown role"):
        return say("S6-A10", "BLOCKED", "unknown role rejected")
    return say("S6-A10", "NOT BLOCKED", "unknown role accepted")


def check_a11():
    text = (
        "## Rules\n\n"
        "### DES-01 — Example\n"
        "```keys\n"
        "kind: judgment\n"
        "severity: advice\n"
        "rule: Do the thing.\n"
        "flag: It breaks the contract.\n"
        "noflag: It matches the contract.\n"
        "source: Fixture source\n"
        "```\n"
    )
    if _must_reject(text, "### DES-01", "orphan"):
        return say("S6-A11", "BLOCKED", "orphan rule rejected")
    return say("S6-A11", "NOT BLOCKED", "orphan accepted")


def check_a12():
    text = document(
        base_rule("DES-01", extra="merges: CMP-09")
        + "\n"
        + base_rule("DES-03", extra="merges: CMP-09")
    )
    err = rejected(text)
    second = text.find("### DES-03")
    line = text[:second].count("\n") + 1
    if err is not None and err.line == line and "conflicting merge" in err.message:
        return say("S6-A12", "BLOCKED", "conflicting merge rejected")
    return say("S6-A12", "NOT BLOCKED", "conflicting merge accepted")


def check_a13():
    text = document(base_rule("REA-01", reviewers="auditor"))
    if _must_reject(text, "### REA-01", "forbidden style"):
        return say("S6-A13", "BLOCKED", "style id on a reviewer rejected")
    return say("S6-A13", "NOT BLOCKED", "style id accepted")


def check_a14():
    text = open(ROLES_PY, encoding="utf-8").read()
    if re.search(r"[A-Z]{2,3}-\d{2}", text):
        return say("S6-A14", "NOT BLOCKED", "roles.py lists rule ids")
    if gen.independent_matrix() is not None or not gen.use_source_assignments():
        return say("S6-A14", "NOT BLOCKED", "matrix overrides the source")
    model, _views = rendered()
    for role, expect in EXPECTED.items():
        if set(gen.ids_for(role, model)) != expect:
            return say("S6-A14", "NOT BLOCKED", role)
    return say("S6-A14", "BLOCKED", "membership comes from the source")


def check_a15():
    text = document(
        "### DES-01 — Example\n"
        "```keys\n"
        "kind: judgment\n"
        "severity: block\n"
        "block_when:\n"
        "  bar: demonstrated\n"
        "  condition: Speculative generality.\n"
        "authors: developer\n"
        "reviewers: auditor\n"
        "merges: CMP-02\n"
        "rule: Speculative generality is a defect.\n"
        "flag: It adds an unused layer.\n"
        "noflag: It fits the current layer.\n"
        "source: Fixture source\n"
        "```\n"
    )
    parser_ok = _must_reject(text, "### DES-01", "speculative generality")
    _model, views = rendered()
    body = section(views["developer"], "DES-01")
    rendered_ok = "clause: speculative generality: advice" in body and "clause: speculative generality: block" not in body
    if parser_ok and rendered_ok:
        return say("S6-A15", "BLOCKED", "speculative generality stays advice")
    return say("S6-A15", "NOT BLOCKED", "cmp-02 severity")


def check_a17():
    text = document(
        "### COR-01 — Example\n"
        "```keys\n"
        "kind: judgment\n"
        "severity: block\n"
        "authors: developer\n"
        "reviewers: auditor\n"
        "rule: Do the thing.\n"
        "flag: It breaks the contract.\n"
        "noflag: It matches the contract.\n"
        "source: Fixture source\n"
        "```\n"
    )
    if _must_reject(text, "### COR-01", "evidence bar"):
        return say("S6-A17", "BLOCKED", "block without a bar rejected")
    return say("S6-A17", "NOT BLOCKED", "block without a bar accepted")


CHECKS = (
    ("S6-H1", check_h1),
    ("S6-H2", check_h2),
    ("S6-H3", check_h3),
    ("S6-H4", check_h4),
    ("S6-H5", check_h5),
    ("S6-H6", check_h6),
    ("S6-H7", check_h7),
    ("S6-H8", check_h8),
    ("S6-H9", check_h9),
    ("S6-H10", check_h10),
    ("S6-H11", check_h11),
    ("S6-H12", check_h12),
    ("S6-H13", check_h13),
    ("S6-H14", check_h14),
    ("S6-H15", check_h15),
    ("S6-A1", check_a1),
    ("S6-A2", check_a2),
    ("S6-A3", check_a3),
    ("S6-A4", check_a4),
    ("S6-A5", check_a5),
    ("S6-A6", check_a6),
    ("S6-A7", check_a7),
    ("S6-A8", check_a8),
    ("S6-A9", check_a9),
    ("S6-A10", check_a10),
    ("S6-A11", check_a11),
    ("S6-A12", check_a12),
    ("S6-A13", check_a13),
    ("S6-A14", check_a14),
    ("S6-A15", check_a15),
    ("S6-A17", check_a17),
)


def main():
    ok = True
    for ident, check in CHECKS:
        try:
            if not check():
                ok = False
        except Exception as exc:
            say(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:180])
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
