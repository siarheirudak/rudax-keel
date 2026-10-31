# Setup

`gh` 1.7.0 or newer (`gh --version`), logged in as the owner GitHub account, with admin on the repo (`gh auth login`). Never the agent GitHub account's token. The scripts use `gh api --paginate` and `gh api --jq` (both in 1.7.0). They do not use `gh api --slurp`, which needs 2.48.0. An older `gh` stops at the version check. Upgrade: <https://cli.github.com/>. No config file: the script uses the account that `gh` is logged in as.

From the repository root:

```bash
bash setup/apply-github-rules.sh OWNER/REPO AGENT_LOGIN
bash setup/verify-github-rules.sh OWNER/REPO AGENT_LOGIN
```

Agent harness on this machine: `bash setup/keel-doctor.sh` (suites and the verdict: `bash setup/tests/harness/run-tests.sh`).

`apply-github-rules.sh` also accepts `--accept-risk` and `--rewrite-codeowners`.

Apply is safe to re-run after each layer merge. Settings that already match are left as they are. A missing CODEOWNERS file, or the template's own line, is fixed before `protect-main`. Any other CODEOWNERS content is left in place and that step is FAIL. `protect-main` is still created. Fix the file in a pull request the owner merges. `--rewrite-codeowners` replaces other content only before `protect-main` exists.

Private repository on GitHub Free: rulesets do not exist. Continue only with `--accept-risk`, or by typing `yes`. The ruleset lines stay FAIL.

Logs: `setup/logs/apply-<timestamp>.log` and `setup/logs/verify-<timestamp>.log` (gitignored). Each line links to [docs/why.md](../docs/why.md). The log file is plain text.

- **✅ OK** — just applied.
- **☑️ ALREADY** — was already correct.
- **⏳ NOT YET** — intentionally later. `require-checks` is NOT YET until `checks.yml` and `scope.yml` are on the default branch and every require-checks context has been reported by GitHub Actions app 15368. The reason lists the names that reported and the names still missing.
- **❌ FAIL** — not done. The script exits non-zero if any step is FAIL. A line that names a Settings page is a manual step the API cannot do.
- **⚠️ WARN** — noted, and the script still exits zero if nothing else failed. Verify uses this when the latest `checks` push to the default branch is red. A red pull request run does not count.

On a terminal, the emoji stands in front of the status word in each step line and in the summary. The word itself stays, so a search for `OK` or `NOT YET` still matches. When stdout is not a terminal, the lines are plain text. `--no-emoji`, or `NO_EMOJI=1`, forces plain text on a terminal too. Apply and verify use the same marks.

When any step is NOT YET, apply prints a separate block after the summary. The block names what is not ready and why, then this line: `run setup/apply-github-rules.sh again after the first pull request has run the checks`. NOT YET does not by itself make the exit code non-zero. The usual case is `require-checks`. After `checks.yml` and `scope.yml` are on the default branch, open a pull request so those checks run, then run apply again. That second run creates `require-checks` once both names have been reported.

An unpinned `uses:` is OK with a reason starting `warning:`.

- Not an admin: `gh auth login` as the owner GitHub account that administers the repo.
- Empty repo: push an initial commit to the default branch, then re-run.
- Invite pending: the agent GitHub account must accept the collaborator invitation.
- Agent has admin: FAIL. Apply does not change the role. Change it to write yourself.
- Private repository: fork approval is OK, reason `not applicable (private repo)`.

Sandbox test: [TESTING.md](TESTING.md).
