#!/usr/bin/env python3
"""Fake gh for setup script tests. Never talks to GitHub."""

import base64
import json
import os
import re
import sys

ROLE = {
    "pull": "read",
    "push": "write",
    "admin": "admin",
    "maintain": "maintain",
    "triage": "triage",
}


def state_path():
    path = os.environ.get("GH_MOCK_STATE")
    if not path:
        sys.stderr.write("GH_MOCK_STATE is not set\n")
        sys.exit(99)
    return path


def load():
    with open(state_path(), encoding="utf-8") as handle:
        return json.load(handle)


def save(state):
    with open(state_path(), "w", encoding="utf-8") as handle:
        json.dump(state, handle)


def log_line(method, path):
    log_path = os.environ.get("GH_MOCK_LOG")
    if not log_path:
        return
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(f"{method} {path}\n")


def default_state():
    return {
        "login": "owner",
        "plan": "pro",
        "org_plan": None,
        "private": False,
        "owner_type": "User",
        "owner_login": "owner",
        "admin": True,
        "default_branch": "main",
        "empty": False,
        "ruleset_list_status": 200,
        "rulesets": [],
        "next_id": 1,
        "collaborators": {},
        "invitations": [],
        "files": {},
        "codeowners_put_status": 201,
        "workflow_perms": {
            "default_workflow_permissions": "write",
            "can_approve_pull_request_reviews": True,
        },
        "fork_policy": "first_time_contributors",
        "fork_status": 200,
        "actions_enabled": True,
        "allowed_actions": "all",
        "selected": {
            "github_owned_allowed": False,
            "verified_allowed": False,
            "patterns_allowed": [],
        },
        "calls": [],
    }


def parse(argv):
    method = None
    slurp = False
    input_file = None
    fields = {}
    endpoint = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--method":
            method = argv[index + 1].upper()
            index += 2
        elif arg == "--paginate":
            index += 1
        elif arg == "--slurp":
            slurp = True
            index += 1
        elif arg == "--input":
            input_file = argv[index + 1]
            index += 2
        elif arg in ("-f", "-F", "--raw-field"):
            key, value = argv[index + 1].split("=", 1)
            fields[key] = value
            index += 2
        elif arg == "--jq":
            index += 2
        elif arg.startswith("-"):
            sys.stderr.write(f"mock unknown flag {arg}\n")
            sys.exit(99)
        else:
            if endpoint is None:
                endpoint = arg
            index += 1
    body = None
    if input_file:
        with open(input_file, encoding="utf-8") as handle:
            body = json.load(handle)
    if method is None:
        method = "POST" if (fields or input_file) else "GET"
    if endpoint is None:
        sys.stderr.write("mock missing endpoint\n")
        sys.exit(99)
    return method, endpoint.split("?", 1)[0], slurp, fields, body


def wrapped_b64(text):
    raw = base64.b64encode(text.encode()).decode()
    return "\n".join(raw[i : i + 60] for i in range(0, len(raw), 60))


def repo_rest(path):
    match = re.fullmatch(r"repos/([^/]+)/([^/]+)(?:/(.*))?", path)
    if not match:
        return None
    return match.group(3) or ""


def emit(code, payload, slurp):
    if code == 204:
        return 0
    if code == 99:
        sys.stderr.write(str(payload) + "\n")
        return 99
    if code >= 400:
        sys.stdout.write(json.dumps({"message": payload}))
        sys.stderr.write(f"gh: {payload} (HTTP {code})\n")
        return 1
    if slurp and isinstance(payload, list):
        text = json.dumps([payload])
    else:
        text = json.dumps(payload)
    sys.stdout.write(text)
    return 0


def route(state, method, path, fields, body):
    if path == "user":
        if method != "GET":
            return 99, f"mock unknown {method} {path}", False
        return 200, {"login": state["login"], "id": 1, "plan": {"name": state["plan"]}}, False

    org = re.fullmatch(r"orgs/([^/]+)", path)
    if org:
        if method != "GET":
            return 99, f"mock unknown {method} {path}", False
        return 200, {"login": org.group(1), "plan": {"name": state.get("org_plan")}}, False

    rest = repo_rest(path)
    if rest is None:
        return 99, f"mock unknown {method} {path}", False

    if rest == "":
        if method != "GET":
            return 99, f"mock unknown {method} {path}", False
        private = bool(state["private"])
        return 200, {
            "private": private,
            "visibility": "private" if private else "public",
            "default_branch": state["default_branch"],
            "permissions": {"admin": bool(state["admin"]), "push": True, "pull": True},
            "owner": {"login": state["owner_login"], "type": state["owner_type"]},
        }, False

    if rest.startswith("commits/"):
        if state["empty"]:
            return 409, "Git Repository is empty.", False
        return 200, {"sha": "abc123"}, False

    if rest == "rulesets":
        if method == "GET":
            status = int(state.get("ruleset_list_status", 200))
            if status != 200:
                return 403, "Upgrade to GitHub Pro to use rulesets on private repositories", False
            return 200, state["rulesets"], True
        if method == "POST":
            item = json.loads(json.dumps(body))
            item["id"] = state["next_id"]
            state["next_id"] += 1
            item["source_type"] = "Repository"
            state["rulesets"].append(item)
            return 201, item, False
        return 99, f"mock unknown {method} {path}", False

    ruleset_id = re.fullmatch(r"rulesets/(\d+)", rest)
    if ruleset_id:
        wanted = int(ruleset_id.group(1))
        found = next((item for item in state["rulesets"] if item["id"] == wanted), None)
        if found is None:
            return 404, "Not Found", False
        if method == "GET":
            return 200, found, False
        if method == "PUT":
            updated = json.loads(json.dumps(body))
            updated["id"] = wanted
            updated["source_type"] = "Repository"
            state["rulesets"] = [updated if item["id"] == wanted else item for item in state["rulesets"]]
            return 200, updated, False
        return 99, f"mock unknown {method} {path}", False

    if rest == "invitations":
        if method != "GET":
            return 99, f"mock unknown {method} {path}", False
        return 200, state["invitations"], True

    permission = re.fullmatch(r"collaborators/([^/]+)/permission", rest)
    if permission:
        login = permission.group(1)
        collab = state["collaborators"].get(login)
        if collab is None:
            return 404, "Not Found", False
        return 200, collab, False

    collaborator = re.fullmatch(r"collaborators/([^/]+)", rest)
    if collaborator:
        login = collaborator.group(1)
        if method == "GET":
            if login not in state["collaborators"]:
                return 404, "Not Found", False
            return 204, None, False
        if method == "PUT":
            perm = fields.get("permission", "push")
            role = ROLE.get(perm, perm)
            if login in state["collaborators"]:
                state["collaborators"][login] = {"permission": role, "role_name": role}
                return 200, {"permission": role, "role_name": role}, False
            state["invitations"].append({"invitee": {"login": login}, "permissions": perm})
            return 201, {"id": 1, "invitee": {"login": login}, "permissions": perm}, False
        return 99, f"mock unknown {method} {path}", False

    if rest.startswith("contents/"):
        content_path = rest[len("contents/") :]
        if method == "GET" and content_path == ".github/workflows":
            prefix = ".github/workflows/"
            entries = []
            for name in sorted(state["files"]):
                if name.startswith(prefix) and "/" not in name[len(prefix) :]:
                    entries.append({"name": name[len(prefix) :], "path": name, "type": "file"})
            if not entries:
                return 404, "Not Found", False
            return 200, entries, False
        if method == "GET":
            text = state["files"].get(content_path)
            if text is None:
                return 404, "Not Found", False
            return 200, {
                "type": "file",
                "encoding": "base64",
                "path": content_path,
                "name": content_path.rsplit("/", 1)[-1],
                "sha": "file",
                "content": wrapped_b64(text),
            }, False
        if method == "PUT":
            if content_path == ".github/CODEOWNERS" and int(state.get("codeowners_put_status", 201)) != 201:
                return int(state["codeowners_put_status"]), (
                    "Repository rule violations found. Changes must be made through a pull request."
                ), False
            if content_path in state["files"] and body.get("sha") != "file":
                return 422, '"sha" wasn\'t supplied.', False
            encoded = body.get("content", "")
            state["files"][content_path] = base64.b64decode(encoded).decode()
            return 201, {"path": content_path}, False
        return 99, f"mock unknown {method} {path}", False

    if rest == "actions/permissions/workflow":
        if method == "GET":
            return 200, state["workflow_perms"], False
        if method == "PUT":
            state["workflow_perms"] = {
                "default_workflow_permissions": body["default_workflow_permissions"],
                "can_approve_pull_request_reviews": body["can_approve_pull_request_reviews"],
            }
            return 200, state["workflow_perms"], False
        return 99, f"mock unknown {method} {path}", False

    if rest == "actions/permissions/fork-pr-contributor-approval":
        status = int(state.get("fork_status", 200))
        if status == 404:
            return 404, "Not Found", False
        if method == "GET":
            return 200, {"approval_policy": state["fork_policy"]}, False
        if method == "PUT":
            state["fork_policy"] = body["approval_policy"]
            return 200, {"approval_policy": state["fork_policy"]}, False
        return 99, f"mock unknown {method} {path}", False

    if rest == "actions/permissions/selected-actions":
        if state.get("allowed_actions") != "selected":
            return 422, "Validation Failed: allowed_actions must be selected", False
        if method == "GET":
            return 200, state["selected"], False
        if method == "PUT":
            state["selected"] = {
                "github_owned_allowed": body["github_owned_allowed"],
                "verified_allowed": body["verified_allowed"],
                "patterns_allowed": body.get("patterns_allowed") or [],
            }
            return 200, state["selected"], False
        return 99, f"mock unknown {method} {path}", False

    if rest == "actions/permissions":
        if method == "GET":
            return 200, {
                "enabled": state["actions_enabled"],
                "allowed_actions": state["allowed_actions"],
            }, False
        if method == "PUT":
            state["actions_enabled"] = body["enabled"]
            state["allowed_actions"] = body["allowed_actions"]
            return 200, {
                "enabled": state["actions_enabled"],
                "allowed_actions": state["allowed_actions"],
            }, False
        return 99, f"mock unknown {method} {path}", False

    return 99, f"mock unknown {method} {path}", False


def main():
    if sys.argv[1:] == ["--init"]:
        save(default_state())
        return 0
    if len(sys.argv) < 2 or sys.argv[1] != "api":
        sys.stderr.write("mock: only gh api is implemented\n")
        return 99
    method, path, slurp, fields, body = parse(sys.argv[2:])
    state = load()
    state["calls"].append({"method": method, "path": path, "body": body, "fields": fields})
    log_line(method, path)
    code, payload, _route_slurp = route(state, method, path, fields, body)
    save(state)
    return emit(code, payload, slurp)


if __name__ == "__main__":
    sys.exit(main())
