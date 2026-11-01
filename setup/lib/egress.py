#!/usr/bin/env python3
"""Allow profiles for the egress forward proxy.

One destination per line: host or host:port. Blank lines and # comments
are ignored. Globs are refused. Hosts are matched after normalize.
"""

import datetime
import json
import os
import re
import sys

GLOB_CHARS = set("*?[]")
HOST_CHARS = re.compile(r"^[A-Za-z0-9.\-:]+$")
MAX_HOST = 253


class ProfileError(Exception):
    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__(code)


def normalize_host(host):
    if host is None:
        raise ProfileError("malformed_profile", "empty host")
    text = str(host).strip()
    if text.endswith("."):
        text = text[:-1]
    if text == "" or any(ch in text for ch in "\r\n\x00 \t/\\"):
        raise ProfileError("malformed_profile", "bad host")
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    try:
        text = text.encode("idna").decode("ascii")
    except UnicodeError:
        raise ProfileError("malformed_profile", "idna")
    return text.lower()


def parse_destination(line, filename, lineno):
    raw = line.strip()
    if raw == "" or raw.startswith("#"):
        return None
    if any(ch in raw for ch in GLOB_CHARS) or ".." in raw or "/" in raw:
        raise ProfileError("malformed_profile", "{0}:{1}".format(filename, lineno))
    host_part, port = raw, None
    if raw.startswith("["):
        end = raw.find("]")
        if end < 0:
            raise ProfileError("malformed_profile", "{0}:{1}".format(filename, lineno))
        host_part = raw[: end + 1]
        rest = raw[end + 1 :]
        if rest:
            if not rest.startswith(":") or not rest[1:].isdigit():
                raise ProfileError("malformed_profile", "{0}:{1}".format(filename, lineno))
            port = int(rest[1:])
    elif raw.count(":") > 1:
        raise ProfileError("malformed_profile", "{0}:{1}".format(filename, lineno))
    elif ":" in raw:
        host_part, port_text = raw.rsplit(":", 1)
        if not port_text.isdigit():
            raise ProfileError("malformed_profile", "{0}:{1}".format(filename, lineno))
        port = int(port_text)
    if port is not None and (port < 1 or port > 65535):
        raise ProfileError("malformed_profile", "{0}:{1}".format(filename, lineno))
    try:
        host = normalize_host(host_part)
    except ProfileError:
        raise ProfileError("malformed_profile", "{0}:{1}".format(filename, lineno))
    if host == "":
        raise ProfileError("malformed_profile", "{0}:{1}".format(filename, lineno))
    return host, port


def parse_allow(text, filename):
    entries = []
    for lineno, line in enumerate(text.splitlines(), 1):
        item = parse_destination(line, filename, lineno)
        if item is not None:
            entries.append(item)
    return entries


def load_profile(path):
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        raise ProfileError("profile_missing", path)
    return parse_allow(text, os.path.basename(path))


def decide_exact(entries, host):
    wanted = normalize_host(host)
    for listed, _port in entries:
        if listed == wanted:
            return True
    return False


def host_allowed(entries, host):
    return decide_exact(entries, host)  # egress-exact


def default_port(kind, port):
    if kind == "connect" and port == 443:
        return True
    return kind == "http" and port == 80


def decide_port(entries, host, port, kind):
    wanted = normalize_host(host)
    seen = False
    for listed, listed_port in entries:
        if listed != wanted:
            continue
        seen = True
        if listed_port is None:
            if default_port(kind, port):
                return True
            continue
        if listed_port == port:
            return True
    # A widened host match that is not an exact list entry still uses the
    # default ports. Exact matching never reaches this for an unlisted host.
    if seen or not host_allowed(entries, host):
        return False
    return default_port(kind, port)


def port_allowed(entries, host, port, kind):
    return decide_port(entries, host, port, kind)  # egress-ports


def destination_allowed(entries, host, port, kind):
    if not host_allowed(entries, host):
        return False
    return port_allowed(entries, host, port, kind)


def clean_host(host):
    text = str(host)
    if any(ch in text for ch in "\r\n\x00"):
        return "invalid"
    text = text.strip()
    if text.startswith("[") and "]" in text:
        text = text[1 : text.index("]")]
    try:
        text = text.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return "invalid"
    if text.endswith("."):
        text = text[:-1]
    if text == "" or not HOST_CHARS.match(text) or len(text) > MAX_HOST:
        return "invalid"
    return text


def sanitize_host(host):
    return clean_host(host)  # egress-sanitize


def denial_log_on():
    return True  # egress-log-on


def log_mode():
    return "hostport"  # egress-log-hostport


def format_target(host, port, raw_url=""):
    if log_mode() == "url" and raw_url:
        return raw_url.replace("\r", "").replace("\n", "").replace("\x00", "")[:500]
    safe = sanitize_host(host)
    try:
        number = int(port)
    except (TypeError, ValueError):
        number = 0
    if number < 1 or number > 65535:
        number = 0
    return "{0}:{1}".format(safe, number)


def log_denial(keel, role, host, port, reason, raw_url=""):
    if not denial_log_on():
        return
    record = {
        "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": "deny",
        "role": role or "",
        "host": format_target(host, port, raw_url),
        "reason": reason,
    }
    line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
    if "\n" in line or "\r" in line:
        record["host"] = "invalid:0"
        record["reason"] = "bad_host"
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
    override = os.environ.get("KEEL_EGRESS_LOG", "")
    path = override if override else os.path.join(keel, ".keel", "logs", "egress.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    handle = os.open(path, flags, 0o666)
    try:
        os.write(handle, (line + "\n").encode("ascii"))
    finally:
        os.close(handle)


def profile_path(harness, role):
    return os.path.join(harness, "egress", role + ".allow")


def check_profile(harness, role):
    path = profile_path(harness, role)
    if not os.path.isfile(path):
        raise ProfileError("profile_missing", path)
    load_profile(path)


def self_test():
    text = "# c\n\nkeel-mock\nexample.com:22\n"
    entries = parse_allow(text, "developer.allow")
    assert ("keel-mock", None) in entries
    assert destination_allowed(entries, "KEEL-MOCK.", 80, "http")
    assert destination_allowed(entries, "keel-mock", 443, "connect")
    assert not destination_allowed(entries, "keel-mock", 22, "connect")
    assert destination_allowed(entries, "example.com", 22, "connect")
    assert not destination_allowed(entries, "evil.keel-mock", 80, "http")
    assert not destination_allowed(entries, "example.com", 80, "http")
    assert normalize_host("Bücher.de.") == "xn--bcher-kva.de"
    assert sanitize_host("evil\r\nsecond") == "invalid"
    assert format_target("example.com", 80) == "example.com:80"
    try:
        parse_allow("*.example.com\n", "bad.allow")
        raise SystemExit("glob accepted")
    except ProfileError as err:
        assert err.code == "malformed_profile"
    print("egress self-test ok")
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        sys.stderr.write("usage: egress.py self-test | check --harness H --role R | deny --keel P --role R --host H --port P --reason C\n")
        return 2
    if argv[1] == "self-test":
        return self_test()
    args = {}
    i = 2
    while i + 1 < len(argv):
        args[argv[i]] = argv[i + 1]
        i += 2
    if argv[1] == "check":
        try:
            check_profile(args.get("--harness", ""), args.get("--role", ""))
        except ProfileError as err:
            sys.stdout.write("REFUSE\t{0}\t{1}\n".format(err.code, err.detail))
            return 1
        sys.stdout.write("ok\n")
        return 0
    if argv[1] == "deny":
        log_denial(
            args.get("--keel", ""),
            args.get("--role", ""),
            args.get("--host", ""),
            args.get("--port", "0"),
            args.get("--reason", "denied"),
        )
        return 0
    sys.stderr.write("unknown command\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
