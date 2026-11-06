"""Role enum and rendering helpers for the standards views.

Membership is not stored here. A view's rules come from the source file.
"""

FAMILIES = (
    "DES",
    "CMP",
    "SCO",
    "TYP",
    "REL",
    "TST",
    "COR",
    "ERR",
    "SEC",
    "DOC",
    "STY",
    "DUP",
    "CX",
    "REA",
    "DAT",
    "API",
    "RES",
)

ROLES = (
    "developer",
    "architect",
    "tester",
    "auditor",
    "design_reviewer",
    "static_gate",
)

MODEL_ROLES = (
    "developer",
    "architect",
    "tester",
    "auditor",
    "design_reviewer",
)

REVIEWERS = (
    "architect",
    "auditor",
    "design_reviewer",
)

ASSIGNMENT_ROLES = (
    "developer",
    "architect",
    "tester",
    "auditor",
    "design_reviewer",
)

DESCRIPTIONS = {
    "developer": "Authoring guidance from the quality standard for the developer.",
    "architect": "Design guidance from the quality standard for the architect.",
    "tester": "Test-authoring guidance from the quality standard for the tester.",
    "auditor": "Review guidance from the quality standard for the auditor.",
    "design_reviewer": "Implementation-fit guidance from the quality standard for the design reviewer.",
    "static_gate": "Mechanical gate facets from the quality standard.",
}


def family_of(rule_id):
    return rule_id.split("-", 1)[0]


def sort_key(rule_id):
    family, number = rule_id.split("-", 1)
    return (FAMILIES.index(family), int(number))


def skill_name(role):
    return "keel-standards-" + role


def front_matter(role):
    return "---\nname: {0}\ndescription: {1}\n---".format(
        skill_name(role), DESCRIPTIONS[role]
    )


def generated_banner():
    return "Generated from standards/rules.md — do not edit"


def reviewers_leave_alone():
    return "Reviewers do not flag formatting, style, or naming."
