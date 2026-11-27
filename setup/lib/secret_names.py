"""Shared secret-name list for redaction and the launch tests.

Values are not read. This module does not start a process.
"""

import re
import sys

# Today's exact names, plus the launch names that are not already in that list.
EXACT = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "BOT_GH_TOKEN",
    "GITHUB_PAT",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "API_KEY",
    "API_TOKEN",
    "NPM_TOKEN",
    "PYPI_TOKEN",
    "PASSWORD",
    "OPENAI_API_KEY",
    "KEEL_SECRET",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "CODEX_ACCESS_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_AUTH_TOKEN",
    "SSH_AUTH_SOCK",
    "GIT_ASKPASS",
)

PATTERN = re.compile(r"(?i)(^|_)(TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY|AUTH)(_|$)")


def is_secret_name(name):
    if not isinstance(name, str) or name == "":
        return False
    if name in EXACT:
        return True
    return PATTERN.search(name) is not None


def main(argv):
    if len(argv) == 3 and argv[1] == "is-secret":
        return 0 if is_secret_name(argv[2]) else 1
    if len(argv) >= 2 and argv[1] == "keep-names":
        kept = [name for name in argv[2:] if name != "" and not is_secret_name(name)]
        sys.stdout.write(" ".join(kept))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
