#!/usr/bin/env python3
"""Literal mutant definitions. Parsed, never imported from a pull request."""
import ast
import re

ID_RE = re.compile(r"^M[0-9]{2,}$")
ALLOWED_NAMES = frozenset({"K"})
WATCH = frozenset({
    "K",
    "M",
    "SUITE_OF",
    "EXTRA_EDITS",
    "COPY_LIST",
    "CI_IDS",
    "OFFLINE_IDS",
    "FULL_ONLY",
    "EXPECTED_MASKED",
    "RED_COUNTS",
    "META",
    "KNOWN_DUPLICATES",
    "FILES",
    "DEPENDS",
    "SUITES",
    "BOOTSTRAP_FULL_RUNS",
})
ID_MAPS = frozenset({
    "M",
    "SUITE_OF",
    "EXTRA_EDITS",
    "META",
    "FILES",
    "EXPECTED_MASKED",
})
CRITICALITY = frozenset({
    "decision",
    "fail-closed",
    "secret",
    "egress",
    "visibility",
    "audit",
    "resource",
    "mechanism",
})
FROZEN_DUPLICATES = (
    ("M23", "M82"),
    ("M24", "M83"),
    ("M25", "M84"),
)

include_forced = True  # plan-forced
use_main = True  # new-against-main
compare_values = True  # compare-values
reject_computed = True  # parser-computed
reject_second = True  # parser-second
reject_names = True  # parser-names
reject_removed = True  # reject-removed
compare_suite = True  # compare-suite
copy_widens = True  # copy-widens
reject_unknown_suite = True  # suite-known
check_duplicates = True  # duplicate-def
reject_new_masked = True  # new-masked
run_coverage_safety = True  # coverage-safety
check_classification = True  # class-check


class DefsError(Exception):
    pass


def id_key(mid):
    return int(mid[1:])


def _eval_node(node, constants):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, bool)) or node.value is None:
            return node.value
        raise DefsError("non-literal")
    if isinstance(node, ast.Name):
        if reject_names and node.id not in ALLOWED_NAMES:
            raise DefsError("name")
        if node.id not in constants:
            if reject_names:
                raise DefsError("name")
            return node.id
        return constants[node.id]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval_node(item, constants) for item in node.elts]
    if isinstance(node, ast.Dict):
        out = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None or not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                if reject_computed:
                    raise DefsError("computed key")
                key = "M00"
            else:
                key = key_node.value
            out[key] = _eval_node(value_node, constants)
        return out
    if reject_computed:
        raise DefsError("non-literal")
    if isinstance(node, ast.Call):
        return {}
    return "M00"


def parse_literals(source):
    """Return watched names. A bad literal, computed key, or second assignment fails."""
    try:
        tree = ast.parse(source)
    except SyntaxError as err:
        raise DefsError("syntax") from err
    constants = {}
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in WATCH:
            continue
        name = target.id
        if name in found:
            if reject_second:
                raise DefsError("second assignment")
        value = _eval_node(node.value, constants)
        if name == "K":
            if not isinstance(value, str):
                raise DefsError("name")
            constants["K"] = value
        found[name] = value
        if name in ID_MAPS and isinstance(value, dict):
            for key in value:
                if not isinstance(key, str) or not ID_RE.fullmatch(key):
                    raise DefsError("id")
    return found


def _tuple(value):
    if isinstance(value, list):
        return tuple(_tuple(item) for item in value)
    return value


def _exp(spec):
    if not isinstance(spec, (list, tuple)) or len(spec) < 5:
        raise DefsError("mutant")
    exp = spec[4]
    if not isinstance(exp, (list, tuple)) or not all(isinstance(item, str) for item in exp):
        raise DefsError("mutant")
    return list(exp)


class Defs(object):
    def __init__(self, literals):
        self.raw = literals
        self.M = literals.get("M") or {}
        self.suite_of = literals.get("SUITE_OF") or {}
        self.extra = literals.get("EXTRA_EDITS") or {}
        self.copy = list(literals.get("COPY_LIST") or [])
        self.ci = list(literals.get("CI_IDS") or [])
        self.offline = list(literals.get("OFFLINE_IDS") or [])
        self.full_only = list(literals.get("FULL_ONLY") or [])
        self.masked = dict(literals.get("EXPECTED_MASKED") or {})
        self.meta = dict(literals.get("META") or {})
        self.files = dict(literals.get("FILES") or {})
        self.ids = set(self.M)

    def edit(self, mid):
        spec = self.M[mid]
        extra_pairs = _tuple(spec[5]) if len(spec) > 5 else ()
        return (spec[0], spec[1], spec[2], extra_pairs, tuple(_exp(spec)))

    def suite(self, mid):
        return self.suite_of.get(mid)

    def extras(self, mid):
        value = self.extra.get(mid) or []
        return tuple(value)


def load_mutate(source):
    found = parse_literals(source)
    for name in ("M", "SUITE_OF", "EXTRA_EDITS", "COPY_LIST"):
        if name not in found:
            raise DefsError("missing " + name)
    if not isinstance(found["M"], dict) or not isinstance(found["SUITE_OF"], dict):
        raise DefsError("mutant")
    if not isinstance(found["EXTRA_EDITS"], dict) or not isinstance(found["COPY_LIST"], list):
        raise DefsError("mutant")
    return Defs(found)


def new_ids(main_ids, pr_ids):
    base = set(main_ids) if use_main else set(pr_ids)
    return set(pr_ids) - base


def removed_ids(main_ids, pr_ids):
    gone = set(main_ids) - set(pr_ids)
    if not reject_removed:
        return []
    return sorted(gone, key=id_key)


def modified_ids(main, pr):
    shared = set(main.ids) & set(pr.ids)
    modified = set()
    for mid in shared:
        if compare_values and main.edit(mid) != pr.edit(mid):
            modified.add(mid)
        if compare_suite:
            if main.suite(mid) != pr.suite(mid) or main.extras(mid) != pr.extras(mid):
                modified.add(mid)
            for other in pr.extras(mid):
                if other in shared and main.edit(other) != pr.edit(other):
                    modified.add(mid)
    if copy_widens and list(main.copy) != list(pr.copy):
        modified |= set(pr.ids)
    return modified


def unknown_suites(suite_of, known):
    if not reject_unknown_suite:
        return []
    known_set = set(known)
    return sorted((mid for mid, suite in suite_of.items() if suite not in known_set), key=id_key)


def classification_errors(ids, ci, offline, full_only):
    if not check_classification:
        return []
    lists = (set(ci), set(offline), set(full_only))
    bad = []
    for mid in ids:
        if sum(mid in group for group in lists) != 1:
            bad.append(mid)
    return bad


def grade_exp(mid, main, pr, masked):
    """Expected attacks for grading. Existing ids come from main."""
    pr_exp = _exp(pr.M[mid]) if mid in pr.M else []
    if mid not in main.ids:
        if reject_new_masked and pr_exp == [] and mid not in masked:
            raise DefsError("empty exp")
        return list(pr_exp)
    main_exp = _exp(main.M[mid])
    use_exp = main_exp  # exp-from-main
    if set(pr_exp) < set(use_exp):
        raise DefsError("shrunk exp")
    return sorted(set(use_exp) | set(pr_exp))


def counts_used(main_counts, pr_counts):
    return main_counts


def coverage_errors(main, pr, known_suites, masked):
    if not run_coverage_safety:
        return []
    errors = []
    errors.extend(classification_errors(pr.ids, pr.ci, pr.offline, pr.full_only))
    if removed_ids(main.ids, pr.ids):
        errors.append("removed")
    errors.extend(unknown_suites(pr.suite_of, known_suites))
    for mid in sorted(pr.ids, key=id_key):
        try:
            grade_exp(mid, main, pr, masked)
        except DefsError as err:
            errors.append("%s %s" % (mid, err))
    return errors


def build_plan(old_ids, fresh_ids, changed_ids, red, all_ids):
    forced = set()
    if include_forced:
        forced = set(fresh_ids) | set(changed_ids)
    chosen = set(all_ids) if red else set(old_ids) | forced
    return sorted(chosen, key=id_key)


def duplicate_errors(defs, known):
    if not check_duplicates:
        return []
    frozen = tuple(tuple(pair) for pair in known)
    if frozen != FROZEN_DUPLICATES:
        return ["known list"]
    groups = {}
    for mid in defs.ids:
        key = (defs.edit(mid)[:4], defs.suite(mid), defs.extras(mid))
        groups.setdefault(key, []).append(mid)
    found = set()
    for mids in groups.values():
        ordered = tuple(sorted(mids, key=id_key))
        if len(ordered) == 2:
            found.add(ordered)
        elif len(ordered) > 2:
            return ["group"]
    expect = set(FROZEN_DUPLICATES)
    if found != expect:
        return ["duplicates"]
    return []


def meta_errors(meta, m_ids, text_for):
    """Ids above M138 need one anchor and a known criticality."""
    errors = []
    for mid in sorted(m_ids, key=id_key):
        if id_key(mid) <= 138:
            continue
        item = meta.get(mid)
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            errors.append(mid)
            continue
        anchor, criticality = item
        if not isinstance(anchor, str) or not anchor or criticality not in CRITICALITY:
            errors.append(mid)
            continue
        texts = text_for(mid)
        if isinstance(texts, str):
            texts = [texts]
        if not texts or any((text or "").count(anchor) != 1 for text in texts):
            errors.append(mid)
    return errors
