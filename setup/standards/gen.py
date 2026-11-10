#!/usr/bin/env python3
"""Generate per-role standards views from setup/standards/rules.md.

Python stdlib only. No network and no environment reads. Suppression syntax
is rejected. The review step's precondition is an owner-controlled approval
path; this schema does not record one, and a suppression is not authorization.
"""

import difflib
import hashlib
import os
import re
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import roles  # noqa: E402

REVIEW_PRECONDITION = (
    "owner-controlled approval path before a suppression can be authorized"
)

ID_RE = re.compile(r"^[A-Z]{2,3}-\d{2}$")
HEADING_RE = re.compile(r"^### ([A-Z]{2,3}-\d{2}) — (.+)$")
ALIAS_RE = re.compile(r"^### (Q-[A-Z]{2,3}-\d{2}) — (.+)$")
LOOSE_HEADING_RE = re.compile(r"^### (\S+) — (.+)$")
SUPPRESS_LINE_RE = re.compile(
    r"(?i)(?:^|\s)#\s*(?:noqa\b|keel-suppress\b|type:\s*ignore\b)"
)
FORBIDDEN_KEYS = {
    "approval_source",
    "suppress",
    "suppression",
    "skip",
    "ignore",
    "noqa",
    "approval",
}
RULE_KEYS = {
    "kind",
    "severity",
    "authors",
    "reviewers",
    "block_reviewers",
    "gate",
    "merges",
    "only",
    "rule",
    "flag",
    "noflag",
    "source",
    "mechanical",
    "block_when",
}
POLICY_KEYS = {"id", "policy", "source"}
BLOCK_KEYS = {"bar", "condition"}
KINDS = {"judgment", "mechanical", "hybrid"}
SEVERITIES = {"block", "advice", "nit"}
BARS = {"demonstrated", "credible"}
STYLE_REVIEW_IDS = {"REA-01", "REA-02", "REA-04", "CMP-01"}
NEW_IDS = {"DAT-01", "API-01", "RES-01", "SEC-09"}
RESERVED_POLICY = {"SEC-08"}


class StandardsError(Exception):
    def __init__(self, line, message):
        super(StandardsError, self).__init__("{0}: {1}".format(line, message))
        self.line = line
        self.message = message


class Rule(object):
    def __init__(self, ident, title, line, fields):
        self.id = ident
        self.title = title
        self.line = line
        self.kind = fields.get("kind", "")
        self.severity = fields.get("severity", "")
        self.authors = fields.get("authors", ())
        self.reviewers = fields.get("reviewers", ())
        self.block_reviewers = fields.get("block_reviewers", ())
        self.gate = fields.get("gate", "")
        self.merges = fields.get("merges", ())
        self.only = fields.get("only", ())
        self.rule = fields.get("rule", "")
        self.flag = fields.get("flag", "")
        self.noflag = fields.get("noflag", "")
        self.source = fields.get("source", "")
        self.mechanical = fields.get("mechanical", "")
        self.block_when = fields.get("block_when")


class Policy(object):
    def __init__(self, ident, policy, source):
        self.id = ident
        self.policy = policy
        self.source = source


class Model(object):
    def __init__(self, rules, policies):
        self.rules = rules
        self.policies = policies


def exclude_policy_ids():
    return True  # exclude-policy-ids


def apply_merges():
    return True  # apply-merges


def require_examples():
    return True  # require-examples


def honor_only():
    return True  # honor-author-only


def check_extra_files():
    return True  # check-extra-files


def check_fails_on_drift():
    return True  # check-fails-on-drift


def emit_severity():
    return True  # emit-severity


def ids_exclude_nonreview():
    return True  # ids-exclude-nonreview


def stable_order():
    return True  # stable-order


def auditor_keeps_typ03():
    return True  # auditor-keeps-typ03


def architect_gains_tst():
    return False  # architect-no-tst


def auditor_keeps_tst02():
    return True  # auditor-tst02


def project_new_rules():
    return True  # project-new-rules


def emit_retired():
    return False  # no-retired-ids


def validate_assignments():
    return True  # validate-assignments


def reject_style_reviewer():
    return True  # reject-style-reviewer


def use_source_assignments():
    return True  # source-assignments-only


def independent_matrix():
    return None  # no-subset-matrix


def strict_schema():
    return True  # strict-schema


def require_source():
    return True  # require-source


def require_bar():
    return True  # require-evidence-bar


def hide_mechanical_from_models():
    return True  # hide-mechanical


def architect_keeps_cor05():
    return True  # architect-cor05


def api01_roles_ok():
    return True  # api01-role-severity


def fail(line, message):
    raise StandardsError(line, message)


def _split_list(value, line):
    if value == "":
        return ()
    items = []
    for part in value.split(","):
        name = part.strip()
        if name == "":
            fail(line, "empty list entry")
        if name in items:
            fail(line, "duplicate list entry")
        items.append(name)
    return tuple(items)


def _roles(value, line):
    names = _split_list(value, line)
    if validate_assignments():
        for name in names:
            if name not in roles.ASSIGNMENT_ROLES:
                fail(line, "unknown role")
    return names


def parse_block(lines, start_line, allowed):
    data = {}
    index = 0
    while index < len(lines):
        raw = lines[index]
        line_no = start_line + index
        if raw.strip() == "":
            index += 1
            continue
        if raw.startswith(" ") or raw.startswith("\t"):
            fail(line_no, "unexpected indent")
        if SUPPRESS_LINE_RE.search(raw):
            fail(line_no, "suppression syntax is not accepted")
        if ":" not in raw:
            fail(line_no, "expected key")
        key, rest = raw.split(":", 1)
        key = key.strip()
        rest = rest.strip()
        if key in FORBIDDEN_KEYS:
            fail(line_no, "suppression syntax is not accepted")
        if key in data:
            fail(line_no, "duplicate key")
        if strict_schema() and key not in allowed:
            fail(line_no, "unknown key")
        if key == "block_when" and rest == "":
            child_lines = []
            child_start = line_no + 1
            index += 1
            while index < len(lines) and (
                lines[index].startswith(" ") or lines[index].startswith("\t")
            ):
                child_lines.append(lines[index].strip())
                index += 1
            data[key] = parse_block(child_lines, child_start, BLOCK_KEYS)
            continue
        data[key] = rest
        index += 1
    return data


def _fence_blocks(text):
    """Return (preamble_lines, list of (start_line, heading, body_lines))."""
    lines = text.splitlines()
    blocks = []
    index = 0
    current = None
    while index < len(lines):
        line = lines[index]
        number = index + 1
        if SUPPRESS_LINE_RE.search(line):
            fail(number, "suppression syntax is not accepted")
        if line.startswith("### "):
            if current is not None:
                fail(number, "unclosed block")
            current = [number, line, None, []]
            index += 1
            continue
        if line.startswith("```") and current is not None and current[2] is None:
            if line.strip() not in ("```", "```keys"):
                fail(number, "unknown fence")
            current[2] = number + 1
            index += 1
            continue
        if line.strip() == "```" and current is not None and current[2] is not None:
            blocks.append(current)
            current = None
            index += 1
            continue
        if current is not None and current[2] is not None:
            current[3].append(line)
            index += 1
            continue
        index += 1
    if current is not None:
        fail(current[0], "unclosed block")
    return lines, blocks


def _heading_id(heading, line):
    alias = ALIAS_RE.match(heading)
    if alias is not None:
        if validate_assignments():
            fail(line, "id alias collision")
        if strict_schema():
            fail(line, "bad id format")
        return alias.group(1), alias.group(2)
    match = HEADING_RE.match(heading)
    if match is None:
        loose = LOOSE_HEADING_RE.match(heading)
        if strict_schema() or loose is None:
            fail(line, "bad id format")
        return loose.group(1), loose.group(2)
    return match.group(1), match.group(2)


def _section_at(lines, heading_line):
    section = "rules"
    for number, line in enumerate(lines, 1):
        if number >= heading_line:
            break
        if line.strip() == "## NOT-to-flag":
            section = "policy"
        elif line.strip() == "## Rules":
            section = "rules"
    return section


def _build_rule(ident, title, line, fields):
    kind = fields.get("kind", "")
    if kind not in KINDS:
        fail(line, "invalid kind")
    severity = fields.get("severity", "")
    if severity not in SEVERITIES:
        fail(line, "invalid severity")
    if strict_schema():
        if not ID_RE.match(ident):
            fail(line, "bad id format")
        family = ident.split("-", 1)[0]
        if family not in roles.FAMILIES:
            fail(line, "unknown family")
    authors = _roles(fields.get("authors", ""), line)
    reviewers = _roles(fields.get("reviewers", ""), line)
    block_reviewers = _roles(fields.get("block_reviewers", ""), line)
    only = _roles(fields.get("only", ""), line)
    merges = _split_list(fields.get("merges", ""), line)
    if strict_schema():
        for merged in merges:
            if not ID_RE.match(merged):
                fail(line, "bad id format")
            family = merged.split("-", 1)[0]
            if family not in roles.FAMILIES:
                fail(line, "unknown family")
    gate = fields.get("gate", "")
    source = fields.get("source", "")
    if require_source() and source == "":
        fail(line, "missing source")
    flag = fields.get("flag", "")
    noflag = fields.get("noflag", "")
    if require_examples() and kind in ("judgment", "hybrid"):
        if flag == "" or noflag == "":
            fail(line, "missing flag or noflag")
    if kind == "judgment" and fields.get("mechanical", "") != "":
        fail(line, "mechanical body on a judgment rule")
    if kind == "hybrid" and fields.get("mechanical", "") == "":
        fail(line, "missing mechanical body")
    block = fields.get("block_when")
    if block is not None:
        if not isinstance(block, dict):
            fail(line, "invalid block_when")
        bar = block.get("bar", "")
        if bar not in BARS:
            fail(line, "invalid evidence bar")
        if block.get("condition", "") == "":
            fail(line, "missing block condition")
    blocking = severity == "block" or block is not None
    if (
        require_bar()
        and blocking
        and kind != "mechanical"
        and (block is None or block.get("bar", "") not in BARS)
    ):
        fail(line, "block path without an evidence bar")
    if "CMP-02" in merges and severity == "block":
        fail(line, "speculative generality must stay advice")
    if validate_assignments():
        if not authors and not reviewers and gate == "":
            fail(line, "orphan rule")
        for name in block_reviewers:
            if name not in reviewers:
                fail(line, "block reviewer is not a reviewer")
        if only:
            for name in authors:
                if name not in only:
                    fail(line, "author outside only")
            if reviewers:
                fail(line, "reviewer assigned a forbidden style id")
    if reject_style_reviewer() and reviewers:
        if ident in STYLE_REVIEW_IDS or ident.startswith("STY-"):
            fail(line, "reviewer assigned a forbidden style id")
    rule = fields.get("rule", "")
    if rule == "":
        fail(line, "missing rule")
    return Rule(
        ident,
        title,
        line,
        {
            "kind": kind,
            "severity": severity,
            "authors": authors,
            "reviewers": reviewers,
            "block_reviewers": block_reviewers,
            "gate": gate,
            "merges": merges,
            "only": only,
            "rule": rule,
            "flag": flag,
            "noflag": noflag,
            "source": source,
            "mechanical": fields.get("mechanical", ""),
            "block_when": block,
        },
    )


def _build_policy(ident, title, line, fields):
    del title
    policy = fields.get("policy", "")
    source = fields.get("source", "")
    declared = fields.get("id", "")
    if declared != ident:
        fail(line, "policy id mismatch")
    if require_source() and source == "":
        fail(line, "missing source")
    if policy == "":
        fail(line, "missing policy")
    return Policy(ident, policy, source)


def _check_merges(rules):
    if not apply_merges():
        return
    merged = {}
    for rule in rules:
        for ident in rule.merges:
            merged.setdefault(ident, []).append(rule)
    headings = {rule.id: rule for rule in rules}
    for ident, owners in merged.items():
        if ident in headings:
            fail(owners[0].line, "merged id redeclared")
        if len(owners) > 1:
            mechanical = all(owner.kind == "mechanical" for owner in owners)
            if validate_assignments() and not mechanical:
                fail(owners[1].line, "conflicting merge target")


def _check_policy_overlap(rules, policies):
    if not exclude_policy_ids():
        return
    policy_ids = {item.id for item in policies} | set(RESERVED_POLICY)
    for rule in rules:
        if rule.id in policy_ids:
            fail(rule.line, "policy id used as a rule")


def parse(text, path="rules.md"):
    del path
    lines, blocks = _fence_blocks(text)
    rules = []
    policies = []
    seen = set()
    for heading_line, heading, _body_start, body in blocks:
        section = _section_at(lines, heading_line)
        ident, title = _heading_id(heading, heading_line)
        if section == "policy":
            fields = parse_block(body, heading_line + 2, POLICY_KEYS)
            policies.append(_build_policy(ident, title, heading_line, fields))
            continue
        if ident in seen:
            if strict_schema():
                fail(heading_line, "duplicate id")
            continue
        if strict_schema() or ID_RE.match(ident):
            seen.add(ident)
        else:
            seen.add(ident)
        fields = parse_block(body, heading_line + 2, RULE_KEYS)
        rules.append(_build_rule(ident, title, heading_line, fields))
    _check_merges(rules)
    _check_policy_overlap(rules, policies)
    return Model(rules, policies)


def _by_id(model):
    return {rule.id: rule for rule in model.rules}


def _retired_ids(model):
    found = []
    if emit_retired() or not apply_merges():
        for rule in model.rules:
            for ident in rule.merges:
                if ident not in found:
                    found.append(ident)
    return found


def _policy_leak():
    if exclude_policy_ids():
        return []
    return ["SEC-08"]


def _include(rule, role):
    if not project_new_rules() and rule.id in NEW_IDS and role != "developer":
        return False
    if role == "auditor" and rule.id == "TYP-03" and not auditor_keeps_typ03():
        return False
    if role == "auditor" and rule.id == "TST-02" and not auditor_keeps_tst02():
        return False
    if role == "architect" and rule.id == "COR-05" and not architect_keeps_cor05():
        return False
    if role == "developer":
        return "developer" in rule.authors and rule.kind != "mechanical"
    if role == "tester":
        return "tester" in rule.authors and rule.kind != "mechanical"
    if role == "static_gate":
        return rule.gate != ""
    if role in rule.reviewers and rule.kind != "mechanical":
        return True
    return False


def ids_for(role, model):
    if role not in roles.ROLES:
        fail(0, "unknown role")
    if not use_source_assignments():
        matrix = independent_matrix()
        if matrix and role in matrix:
            return ordered(list(matrix[role]))
    found = []
    for rule in model.rules:
        if _include(rule, role) and rule.id not in found:
            found.append(rule.id)
    if architect_gains_tst() and role == "architect" and "TST-01" not in found:
        found.append("TST-01")
    if not honor_only() and role in roles.REVIEWERS:
        for rule in model.rules:
            if rule.only and rule.id not in found:
                found.append(rule.id)
    if not ids_exclude_nonreview() and role in roles.REVIEWERS:
        for rule in model.rules:
            if rule.gate and not rule.reviewers and rule.id not in found:
                found.append(rule.id)
    for ident in _retired_ids(model) + _policy_leak():
        if ident not in found:
            found.append(ident)
    return ordered(found)


def ordered(ids):
    unique = []
    for ident in ids:
        if ident not in unique:
            unique.append(ident)
    if not stable_order():
        return list(set(unique))
    return sorted(unique, key=roles.sort_key)


def _presentation(rule, role):
    if not emit_severity():
        return None
    if rule.id == "API-01" and not api01_roles_ok():
        if role == "auditor":
            return ("advice", None, None)
        if role == "design_reviewer":
            return ("block", "demonstrated", rule.block_when["condition"] if rule.block_when else "")
    if role in rule.reviewers and rule.block_reviewers and role not in rule.block_reviewers:
        return ("advice", None, None)
    bar = None
    condition = None
    if rule.block_when:
        bar = rule.block_when.get("bar")
        condition = rule.block_when.get("condition")
    return (rule.severity, bar, condition)


def _clause_lines(rule):
    if "CMP-02" not in rule.merges:
        return []
    label = "advice" if emit_severity() else "block"
    return [
        "clause: speculative generality: " + label,
        "clause: simple over clever: " + label,
        "clause: system complexity: " + label,
    ]


def _render_model_rule(role, rule):
    lines = ["### {0} — {1}".format(rule.id, rule.title), ""]
    presented = _presentation(rule, role)
    if presented is not None:
        severity, bar, condition = presented
        lines.append("severity: " + severity)
        if bar:
            lines.append("bar: " + bar)
        if condition:
            lines.append("condition: " + condition)
        lines.append("")
    clauses = _clause_lines(rule)
    if clauses:
        lines.extend(clauses)
        lines.append("")
    lines.append(rule.rule)
    lines.append("")
    if rule.kind in ("judgment", "hybrid"):
        lines.append("Flag: " + rule.flag)
        lines.append("")
        lines.append("Do not flag: " + rule.noflag)
        lines.append("")
    if rule.mechanical and not hide_mechanical_from_models():
        lines.append(rule.mechanical)
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def _render_gate_rule(rule):
    if rule.kind == "hybrid":
        body = rule.mechanical
    else:
        body = rule.rule
    lines = [
        "### {0} — {1}".format(rule.id, rule.title),
        "",
        "kind: " + rule.kind,
        "gate: " + rule.gate,
        "",
        body,
    ]
    return "\n".join(lines).rstrip("\n")


def _render_extra(ident):
    return "### {0} — retired".format(ident)


def render_views(model, source_bytes):
    digest = hashlib.sha256(source_bytes).hexdigest()
    lookup = _by_id(model)
    views = {}
    for role in roles.ROLES:
        chunks = [roles.front_matter(role), "", "# " + roles.skill_name(role), ""]
        chunks.append(roles.generated_banner())
        chunks.append("")
        chunks.append("source-sha256: " + digest)
        chunks.append("")
        if role in roles.MODEL_ROLES:
            chunks.append(roles.reviewers_leave_alone())
            chunks.append("")
            chunks.append("## Not to flag")
            chunks.append("")
            for policy in model.policies:
                chunks.append(policy.policy)
                chunks.append("")
        else:
            chunks.append(
                "A required adapter with no tool behind it blocks. "
                "An optional adapter that is not supported is advice and is not a passing check."
            )
            chunks.append("")
        chunks.append("## Rules")
        chunks.append("")
        for ident in ids_for(role, model):
            rule = lookup.get(ident)
            if rule is None:
                chunks.append(_render_extra(ident))
            elif role == "static_gate":
                chunks.append(_render_gate_rule(rule))
            else:
                chunks.append(_render_model_rule(role, rule))
            chunks.append("")
        text = "\n".join(chunks).rstrip("\n") + "\n"
        views[role] = text
    return views


def rules_path():
    return os.path.join(_HERE, "rules.md")


def views_root():
    return os.path.join(_HERE, "views")


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def load(path):
    data = _read_bytes(path)
    text = data.decode("utf-8")
    return parse(text, path), data


def _first_diff(expected, actual):
    exp_lines = expected.splitlines(keepends=True)
    act_lines = actual.splitlines(keepends=True)
    diff = difflib.unified_diff(exp_lines, act_lines, "expected", "actual")
    return "".join(diff)


def audit(model, source_bytes, root):
    if not check_fails_on_drift():
        return 0, ""
    expected = render_views(model, source_bytes)
    for role in roles.ROLES:
        path = os.path.join(root, role, "SKILL.md")
        if not os.path.isfile(path) or os.path.islink(path):
            return 1, _first_diff(expected[role], "")
        actual = _read_bytes(path).decode("utf-8")
        if actual != expected[role]:
            return 1, _first_diff(expected[role], actual)
    if check_extra_files():
        allowed = {role + "/SKILL.md" for role in roles.ROLES}
        if not os.path.isdir(root):
            return 1, "missing views\n"
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(name for name in dirnames if name != "__pycache__")
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                if rel not in allowed:
                    return 1, "extra file: " + rel + "\n"
    return 0, ""


def write_views(views, root):
    os.makedirs(root, exist_ok=True)
    temporary = tempfile.mkdtemp(prefix=".standards-views-", dir=root)
    try:
        for role, text in views.items():
            folder = os.path.join(temporary, role)
            os.makedirs(folder)
            path = os.path.join(folder, "SKILL.md")
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        for role in views:
            target_dir = os.path.join(root, role)
            os.makedirs(target_dir, exist_ok=True)
            os.replace(
                os.path.join(temporary, role, "SKILL.md"),
                os.path.join(target_dir, "SKILL.md"),
            )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main(argv):
    source = rules_path()
    out = views_root()
    args = list(argv[1:])
    if "--source" in args:
        source = args[args.index("--source") + 1]
    if "--out" in args:
        out = args[args.index("--out") + 1]
    try:
        if "--ids" in args:
            role = args[args.index("--ids") + 1]
            model, _data = load(source)
            if role not in roles.ROLES:
                sys.stderr.write("{0}:0: unknown role\n".format(source))
                return 2
            for ident in ids_for(role, model):
                sys.stdout.write(ident + "\n")
            return 0
        model, data = load(source)
        if "--check" in args:
            code, message = audit(model, data, out)
            if message:
                sys.stdout.write(message)
            return code
        write_views(render_views(model, data), out)
    except StandardsError as err:
        sys.stderr.write("{0}:{1}: {2}\n".format(source, err.line, err.message))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
