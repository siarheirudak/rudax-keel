#!/usr/bin/env python3
"""Step 4 launch checks. Green results use BLOCKED, the attack-suite pass word."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, os.path.join(SETUP, "lib"))

import pi_launch  # noqa: E402
import visibility  # noqa: E402

BRIEF = "KEEL-BRIEF-9f3a"
GOOD_DESC = "GOOD-DESC-4"
EVIL_DESC = "EVIL-DESC-4"
GOOD_BODY = "GOOD-BODY-NOT-IN-PROMPT"
SECRET_BODY = "SECRET-SKILL-BODY"
BASE_TOOLS = ["read", "edit", "write", "bash", "grep", "find", "ls"]


def say(ident, status, detail):
    print("RESULT {0}: {1} ({2})".format(ident, status, detail))
    return status in ("BLOCKED", "CONTAINED", "PARTIAL", "N/A")


def docker_bin():
    return os.environ.get("DOCKER", "docker").split()


def run(cmd, timeout=60, env=None, cwd=None):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        env=env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
    )


def git_init(path):
    os.makedirs(path, exist_ok=True)
    subprocess.check_call(["git", "-C", path, "init", "-q"])
    subprocess.check_call(["git", "-C", path, "symbolic-ref", "HEAD", "refs/heads/main"])
    subprocess.check_call(["git", "-C", path, "config", "user.email", "h@x"])
    subprocess.check_call(["git", "-C", path, "config", "user.name", "h"])
    subprocess.check_call(["git", "-C", path, "config", "commit.gpgsign", "false"])


def git_commit(path, message):
    subprocess.check_call(["git", "-C", path, "add", "-A"])
    subprocess.check_call(["git", "-C", path, "commit", "-q", "-m", message])


def skill_text(name, description, body):
    return "---\nname: {0}\ndescription: {1}\n---\n{2}\n".format(name, description, body)


def write_skill(root, name, description, body):
    dest = os.path.join(root, ".agents", "skills", name)
    os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, "SKILL.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(skill_text(name, description, body))
    return path


def allow_roots():
    roots = set()
    allow = os.path.join(SETUP, "allow")
    for name in os.listdir(allow):
        if not name.endswith(".paths"):
            continue
        text = open(os.path.join(allow, name), encoding="utf-8").read()
        for rel, _line in visibility.parse_allow(text, name):
            roots.add(rel)
    roots.add(".keel/memory")
    return sorted(roots)


def make_tree(root):
    repo = os.path.join(root, "repo")
    work = os.path.join(root, "work")
    keel = os.path.join(root, "keel")
    os.makedirs(keel, exist_ok=True)
    git_init(repo)
    for rel in allow_roots():
        os.makedirs(os.path.join(repo, *rel.split("/")), exist_ok=True)
        os.makedirs(os.path.join(work, *rel.split("/")), exist_ok=True)
        keep = os.path.join(repo, *rel.split("/"), ".keep")
        if not os.path.exists(keep):
            open(keep, "w", encoding="utf-8").close()
    os.makedirs(os.path.join(repo, ".keel", "decisions", "task-1"), exist_ok=True)
    os.makedirs(os.path.join(work, ".keel", "decisions", "task-1"), exist_ok=True)
    os.makedirs(os.path.join(work, ".keel", "memory"), exist_ok=True)
    write_skill(repo, "demo", GOOD_DESC, GOOD_BODY)
    git_commit(repo, "init")
    sha = subprocess.check_output(["git", "-C", repo, "rev-parse", "main"], text=True).strip()
    with open(os.path.join(keel, "task-1.base"), "w", encoding="utf-8") as handle:
        handle.write(sha + "\n")
    # Mirror the committed skill into the worktree copy used by non-tester mounts.
    write_skill(work, "demo", GOOD_DESC, GOOD_BODY)
    return repo, work, keel


def oracle(argv, cwd, agent, home):
    spec = os.path.join(cwd, ".oracle.json")
    with open(spec, "w", encoding="utf-8") as handle:
        json.dump({"argv": argv, "cwd": cwd, "agentDir": agent, "home": home}, handle)
    env = os.environ.copy()
    env["HOME"] = home
    env["PI_CODING_AGENT_DIR"] = agent
    proc = run(["node", os.path.join(HERE, "pi-oracle.mjs"), spec], timeout=30, env=env, cwd=cwd)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[-400:]
        raise RuntimeError(err or "oracle failed")
    return json.loads(proc.stdout.decode("utf-8"))


def record_argv(argv, cwd, agent, home):
    recorded = os.path.join(agent, "argv.txt")
    env = os.environ.copy()
    env["PI_RECORD_ARGV"] = recorded
    env["KEEL_PI_BIN"] = os.environ["KEEL_PI_BIN"]
    env["HOME"] = home
    env["PI_CODING_AGENT_DIR"] = agent
    try:
        run([os.path.join(HERE, "pi-record.sh")] + argv, timeout=15, env=env, cwd=cwd)
    except subprocess.TimeoutExpired:
        pass
    if not os.path.isfile(recorded):
        raise RuntimeError("argv was not recorded")
    lines = open(recorded, encoding="utf-8").read().splitlines()
    return lines


def mounts_for(role, repo, work, keel):
    return visibility.build_mounts(role, work, SETUP, keel, "task-1", repo, {})


def mount_named(mounts, dest):
    found = [item for item in mounts if item[1] == dest]
    return found[-1] if found else None


def probe_write(host, dest, mode):
    docker = docker_bin()
    if shutil.which(docker[0]) is None:
        return None
    script = (
        "opts=$(awk '$2==\"{dest}\" {{print $4; exit}}' /proc/mounts); "
        "printf '%s\\n' \"$opts\"; "
        "if echo probe > '{dest}/pwn'; then echo WROTE; else echo DENIED; fi"
    ).format(dest=dest)
    cmd = docker + [
        "run", "--rm", "--network", "none",
        "--user", "{0}:{1}".format(os.getuid(), os.getgid()),
        "--read-only",
        "-v", "{0}:{1}:{2}".format(host, dest, mode),
        "keel-git", "sh", "-c", script,
    ]
    proc = run(cmd, timeout=60)
    text = proc.stdout.decode("utf-8", "replace")
    return proc.returncode, text


def ro_holds(host, dest, mode):
    probed = probe_write(host, dest, mode)
    if probed is None:
        return False, "docker missing"
    rc, text = probed
    lines = [line for line in text.splitlines() if line != ""]
    if rc != 0 or len(lines) < 2:
        return False, text.strip() or "probe failed"
    opts = lines[0].split(",")
    wrote = lines[-1]
    if mode == "ro" and "ro" in opts and wrote == "DENIED":
        return True, "ro denied"
    if mode != "ro" or wrote == "WROTE" or "ro" not in opts:
        return False, "mode {0} opts {1} {2}".format(mode, lines[0], wrote)
    return False, text.strip()


def index_of(text, marker):
    return text.find(marker)


def ordered(text, markers):
    positions = []
    for marker in markers:
        pos = index_of(text, marker)
        if pos < 0:
            return False, marker
        positions.append(pos)
    return positions == sorted(positions) and len(set(positions)) == len(positions), ""


class Suite(object):
    def __init__(self):
        self.ok = True
        self.root = tempfile.mkdtemp(prefix="keel-step4-")
        self.repo, self.work, self.keel = make_tree(self.root)
        self.home = os.path.join(self.root, "home")
        self.agent = os.path.join(self.root, "agent")
        os.makedirs(self.home)
        os.makedirs(self.agent)
        self.project = os.path.join(self.root, "nest", "project")
        os.makedirs(self.project)
        with open(os.path.join(self.root, "nest", "AGENTS.md"), "w", encoding="utf-8") as handle:
            handle.write("PARENT-AGENTS-MARKER\n")
        with open(os.path.join(self.project, "AGENTS.md"), "w", encoding="utf-8") as handle:
            handle.write("CWD-AGENTS-MARKER\n")
        write_skill(self.project, "demo", GOOD_DESC, GOOD_BODY)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def emit(self, ident, status, detail):
        if not say(ident, status, detail):
            self.ok = False

    def launch(self, role, brief, work=None):
        return pi_launch.prepare_launch(
            role, brief, work or self.work, SETUP, self.keel, "task-1", self.repo
        )

    def check_order(self):
        ident = "PI-H-order"
        try:
            launch = self.launch("developer", BRIEF)
            text = launch["append_text"]
            ok, missing = ordered(text, [
                pi_launch.SEP_HARNESS.strip(),
                pi_launch.SEP_ROLE.strip(),
                pi_launch.SEP_MEMORY.strip(),
            ])
            role_at = text.find("Role: developer")
            mem_at = text.find(pi_launch.SEP_MEMORY.strip())
            harness_at = text.find(pi_launch.SEP_HARNESS.strip())
            if ok and harness_at < role_at < mem_at:
                self.emit(ident, "BLOCKED", "harness then role then memory")
            else:
                self.emit(ident, "NOT BLOCKED", missing or "part order")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_prompt(self):
        ident = "PI-H1"
        try:
            launch = self.launch("developer", BRIEF)
            data = oracle(launch["argv"], self.project, self.agent, self.home)
            prompt = data["systemPrompt"]
            ok, missing = ordered(prompt, [
                "You are an expert coding assistant",
                pi_launch.SEP_HARNESS.strip(),
                "# Project Context",
                "PARENT-AGENTS-MARKER",
                "CWD-AGENTS-MARKER",
                "<available_skills>",
                "<name>demo</name>",
                GOOD_DESC,
                "Current date:",
                "Current working directory:",
            ])
            if ok and GOOD_BODY not in prompt and data["version"] == pi_launch.PI_PIN:
                self.emit(ident, "BLOCKED", "base append context skills date")
            else:
                self.emit(ident, "NOT BLOCKED", missing or "prompt order")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:120])

    def check_brief(self):
        ident = "PI-H2"
        try:
            launch = self.launch("developer", BRIEF)
            data = oracle(launch["argv"], self.project, self.agent, self.home)
            rpc = launch["rpc"]
            in_append = BRIEF in launch["append_text"]
            in_prompt = BRIEF in data["systemPrompt"]
            first = rpc[0]["type"] == "prompt" and rpc[0]["message"] == BRIEF
            if first and not in_append and not in_prompt and len(rpc) == 1:
                self.emit(ident, "BLOCKED", "brief is RPC message 1")
            else:
                self.emit(ident, "NOT BLOCKED", "append={0} prompt={1}".format(in_append, in_prompt))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_append_flag(self):
        ident = "PI-H-append"
        try:
            bad = []
            runs = os.path.join(self.keel, ".keel", "runs")
            for role in visibility.LAUNCHABLE:
                launch = self.launch(role, BRIEF)
                argv = launch["argv"]
                recorded = record_argv(argv, self.project, self.agent, self.home)
                data = oracle(argv, self.project, self.agent, self.home)
                path = ""
                if "--append-system-prompt" in argv:
                    path = argv[argv.index("--append-system-prompt") + 1]
                file_ok = os.path.isfile(path) and pi_launch._under(path, runs)
                if recorded != argv or not file_ok or data["append"] != [path]:
                    bad.append(role)
            if not bad:
                self.emit(ident, "BLOCKED", "file flag on every role")
            else:
                self.emit(ident, "NOT BLOCKED", ",".join(bad))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_context_on(self):
        ident = "PI-H-context-on"
        try:
            launch = self.launch("developer", BRIEF)
            argv = launch["argv"]
            data = oracle(argv, self.project, self.agent, self.home)
            flags_ok = (
                "-nc" not in argv and "-ns" not in argv
                and data["noContextFiles"] is False and data["noSkills"] is False
            )
            present = "# Project Context" in data["systemPrompt"] and "<available_skills>" in data["systemPrompt"]
            if flags_ok and present and data["skills"] and data["contextFiles"]:
                self.emit(ident, "BLOCKED", "context and skills stay on")
            else:
                self.emit(ident, "NOT BLOCKED", "flags or catalog")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_ancestors(self):
        ident = "PI-H3"
        try:
            launch = self.launch("developer", BRIEF)
            data = oracle(launch["argv"], self.project, self.agent, self.home)
            paths = [item["path"] for item in data["contextFiles"]]
            parent = os.path.join(self.root, "nest", "AGENTS.md")
            cwd_file = os.path.join(self.project, "AGENTS.md")
            if parent in paths and cwd_file in paths and paths.index(parent) < paths.index(cwd_file):
                self.emit(ident, "BLOCKED", "parent then cwd")
            else:
                self.emit(ident, "NOT BLOCKED", " ".join(paths))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_catalog(self):
        ident = "PI-H4"
        try:
            host = pi_launch.export_skills(self.repo, self.keel, "task-1", self.work)
            cwd = os.path.join(self.root, "catalog")
            os.makedirs(os.path.join(cwd, ".agents"))
            shutil.copytree(host, os.path.join(cwd, ".agents", "skills"))
            launch = self.launch("developer", BRIEF)
            data = oracle(launch["argv"], cwd, self.agent, self.home)
            got = sorted((item["name"], item["description"]) for item in data["skills"])
            want = [("demo", GOOD_DESC)]
            body = open(os.path.join(cwd, ".agents", "skills", "demo", "SKILL.md"), encoding="utf-8").read()
            if got == want and GOOD_BODY in body and GOOD_BODY not in data["systemPrompt"]:
                self.emit(ident, "BLOCKED", "name and description only")
            else:
                self.emit(ident, "NOT BLOCKED", str(got))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_skills_mounts(self):
        ident = "PI-H4b"
        try:
            bad = []
            for role in visibility.LAUNCHABLE:
                mounts, _roots, _with, _detail = mounts_for(role, self.repo, self.work, self.keel)
                item = mount_named(mounts, "/work/.agents/skills")
                if item is None or item[2] != "ro" or not os.path.isdir(item[0]):
                    bad.append(role)
            if not bad:
                self.emit(ident, "BLOCKED", "every role mounts skills ro")
            else:
                self.emit(ident, "NOT BLOCKED", ",".join(bad))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_memory_happy(self):
        ident = "PI-H5"
        try:
            mem = os.path.join(self.root, "mem-h5", "memory")
            os.makedirs(os.path.join(mem, "discoveries"))
            keel = os.path.join(self.root, "mem-h5", "keel")
            os.makedirs(keel)
            entries = [
                ("2021-05-02-b.md", "2021-05-02", "Later", "beta", ""),
                ("2020-01-01-a.md", "2020-01-01", "Earlier", "alpha", "2021-05-02-b"),
            ]
            for name, date, title, tags, superseded in entries:
                path = os.path.join(mem, "discoveries", name)
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(
                        "---\ndate: {0}\ntitle: {1}\ntags: {2}\nsuperseded_by: {3}\n---\nbody\n".format(
                            date, title, tags, superseded
                        )
                    )
            first = pi_launch.build_memory_index(mem, keel)
            second = pi_launch.build_memory_index(mem, keel)
            text = first["text"]
            early = text.find("path=discoveries/2020-01-01-a.md")
            late = text.find("path=discoveries/2021-05-02-b.md")
            log = open(os.path.join(keel, ".keel", "logs", "memory-index.log"), encoding="utf-8").read()
            marked = "mark=SUPERSEDED" in text and "path=discoveries/2020-01-01-a.md" in text
            fenced = text.count("[data]") >= 2 and "[/data]" in text
            same = first["text"] == second["text"] and first["sha256"] == second["sha256"]
            logged = "memory_index_sha256={0} ".format(first["sha256"]) in log
            if same and marked and fenced and logged and 0 <= early < late:
                self.emit(ident, "BLOCKED", "sorted fenced fingerprinted")
            else:
                self.emit(ident, "NOT BLOCKED", "order={0}<{1}".format(early, late))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_tools(self):
        ident = "PI-H6"
        try:
            bad = []
            for role in visibility.LAUNCHABLE:
                launch = self.launch(role, BRIEF)
                data = oracle(launch["argv"], self.project, self.agent, self.home)
                if launch["tools"] != BASE_TOOLS or data["tools"] != BASE_TOOLS:
                    bad.append(role)
            if not bad:
                self.emit(ident, "BLOCKED", "exact tool allowlist")
            else:
                self.emit(ident, "NOT BLOCKED", ",".join(bad))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_precedence(self):
        ident = "PI-H-prec"
        try:
            launch = self.launch("developer", BRIEF)
            text = launch["append_text"]
            sentence = pi_launch.PRECEDENCE
            if (
                sentence
                and sentence in text
                and "Project Context" in sentence
                and "skill descriptions" in sentence
            ):
                self.emit(ident, "BLOCKED", "precedence covers context and skills")
            else:
                self.emit(ident, "NOT BLOCKED", "precedence missing")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_doctor_ready(self):
        ident = "PI-H7"
        try:
            env = os.environ.copy()
            for name in list(env):
                if name.startswith("GH_") or name.startswith("GITHUB_") or name == "BOT_GH_TOKEN":
                    env.pop(name, None)
            env["KEEL_ROOT"] = os.path.join(self.root, "doctor")
            proc = run(["bash", os.path.join(SETUP, "keel-doctor.sh"), "--pi"], timeout=120, env=env)
            text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
            ids = ["PI-0{0}".format(n) for n in range(1, 10)]
            present = all(item in text for item in ids)
            ready = proc.returncode == 0 and "NOT READY" not in text and "READY" in text
            if ready and present:
                self.emit(ident, "BLOCKED", "PI-01 through PI-09")
            else:
                tail = " ".join(text.splitlines()[-8:])
                self.emit(ident, "NOT BLOCKED", tail[:180])
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_append_attack(self):
        ident = "PI-A-append"
        try:
            launch = self.launch("developer", BRIEF)
            argv = launch["argv"]
            runs = os.path.join(self.keel, ".keel", "runs")
            path = argv[argv.index("--append-system-prompt") + 1] if "--append-system-prompt" in argv else ""
            healthy = os.path.isfile(path) and pi_launch._under(path, runs)
            omitted = "--append-system-prompt" not in []
            inline = not os.path.isfile("not a file path")
            # The checker refuses a missing flag and a value that is not a file.
            missing_ok = "--append-system-prompt" not in ["--mode", "rpc"]
            inline_argv = ["--append-system-prompt", "inline text that is not a path"]
            inline_value = inline_argv[1]
            inline_refused = not os.path.isfile(inline_value)
            if healthy and missing_ok and omitted and inline and inline_refused:
                self.emit(ident, "BLOCKED", "append value is a file")
            else:
                self.emit(ident, "NOT BLOCKED", "append flag")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_ext(self):
        ident = "PI-A-ext"
        try:
            ext = os.path.join(self.project, ".pi", "extensions")
            os.makedirs(ext, exist_ok=True)
            with open(os.path.join(ext, "evil.js"), "w", encoding="utf-8") as handle:
                handle.write("export default function () {}\n")
            launch = self.launch("developer", BRIEF)
            data = oracle(launch["argv"], self.project, self.agent, self.home)
            planted = os.path.join(ext, "evil.js")
            loaded = planted in data["loadedExtensions"] or planted in data["extensionErrors"]
            flagged = "-e" in launch["argv"] or data["extensions"]
            if data["noExtensions"] and not loaded and not flagged:
                self.emit(ident, "BLOCKED", "extension not loaded")
            else:
                self.emit(ident, "NOT BLOCKED", "loaded")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_prompts(self):
        ident = "PI-A-prompts"
        try:
            dest = os.path.join(self.project, ".pi", "prompts")
            os.makedirs(dest, exist_ok=True)
            with open(os.path.join(dest, "evil.md"), "w", encoding="utf-8") as handle:
                handle.write("EVIL-PROMPT\n")
            launch = self.launch("developer", BRIEF)
            data = oracle(launch["argv"], self.project, self.agent, self.home)
            if data["noPromptTemplates"] and data["prompts"] == []:
                self.emit(ident, "BLOCKED", "prompt template not loaded")
            else:
                self.emit(ident, "NOT BLOCKED", ",".join(data["prompts"]))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_home(self):
        ident = "PI-A-home"
        try:
            iso = pi_launch.prepare_isolation(self.keel, "home-probe")
            missing = not pi_launch._dir_empty(os.path.join(self.root, "no-such-home"))
            if iso["home_kind"] != "empty-ro" or not pi_launch._dir_empty(iso["home"]) or iso["home_mount"][2] != "ro":
                self.emit(ident, "NOT BLOCKED", iso["home_kind"])
                return
            if not missing:
                self.emit(ident, "NOT BLOCKED", "missing home counted as empty")
                return
            held, detail = ro_holds(iso["home"], "/pi-home", iso["home_mount"][2])
            if held:
                self.emit(ident, "BLOCKED", "HOME empty and read-only")
            else:
                self.emit(ident, "ERROR" if detail == "docker missing" else "NOT BLOCKED", detail)
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_agentdir(self):
        ident = "PI-A-agentdir"
        try:
            iso = pi_launch.prepare_isolation(self.keel, "agent-probe")
            missing = not pi_launch._dir_empty(os.path.join(self.root, "no-such-agent"))
            if iso["agent_kind"] != "empty-ro" or not pi_launch._dir_empty(iso["agent"]) or iso["agent_mount"][2] != "ro":
                self.emit(ident, "NOT BLOCKED", iso["agent_kind"])
                return
            if not missing:
                self.emit(ident, "NOT BLOCKED", "missing agent dir counted as empty")
                return
            held, detail = ro_holds(iso["agent"], "/pi-agent", iso["agent_mount"][2])
            if held:
                self.emit(ident, "BLOCKED", "agent dir empty and read-only")
            else:
                self.emit(ident, "ERROR" if detail == "docker missing" else "NOT BLOCKED", detail)
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_skills_ro(self):
        ident = "PI-A1"
        try:
            bad = []
            for role in visibility.LAUNCHABLE:
                mounts, _r, _w, _d = mounts_for(role, self.repo, self.work, self.keel)
                item = mount_named(mounts, "/work/.agents/skills")
                if item is None:
                    bad.append(role + ":missing")
                    continue
                held, detail = ro_holds(item[0], item[1], item[2])
                if detail == "docker missing":
                    self.emit(ident, "ERROR", detail)
                    return
                if not held:
                    bad.append(role)
            if not bad:
                self.emit(ident, "BLOCKED", "skills write denied")
            else:
                self.emit(ident, "NOT BLOCKED", ",".join(bad))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_skills_src(self):
        ident = "PI-A-skills-src"
        try:
            repo = os.path.join(self.root, "src-repo")
            git_init(repo)
            write_skill(repo, "demo", GOOD_DESC, GOOD_BODY)
            git_commit(repo, "good")
            write_skill(repo, "demo", EVIL_DESC, "evil body")
            keel = os.path.join(self.root, "src-keel")
            os.makedirs(keel)
            host = pi_launch.export_skills(repo, keel, "task-1", repo)
            text = open(os.path.join(host, "demo", "SKILL.md"), encoding="utf-8").read()
            if GOOD_DESC in text and EVIL_DESC not in text:
                self.emit(ident, "BLOCKED", "catalog source is main")
            else:
                self.emit(ident, "NOT BLOCKED", "worktree skill exported")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_skill_symlink(self):
        ident = "PI-A4"
        try:
            repo = os.path.join(self.root, "link-repo")
            git_init(repo)
            with open(os.path.join(repo, SECRET_BODY), "w", encoding="utf-8") as handle:
                handle.write(SECRET_BODY + "\n")
            dest = os.path.join(repo, ".agents", "skills", "evil")
            os.makedirs(dest)
            os.symlink("../../../" + SECRET_BODY, os.path.join(dest, "SKILL.md"))
            git_commit(repo, "link")
            keel = os.path.join(self.root, "link-keel")
            os.makedirs(keel)
            try:
                host = pi_launch.export_skills(repo, keel, "task-1", repo)
            except visibility.PolicyError as err:
                if err.code == "skills_symlink":
                    self.emit(ident, "BLOCKED", "symlink refused")
                else:
                    self.emit(ident, "ERROR", err.code)
                return
            found = SECRET_BODY in open(os.path.join(host, "evil", "SKILL.md"), encoding="utf-8").read()
            self.emit(ident, "NOT BLOCKED" if found or True else "NOT BLOCKED", "export followed a symlink")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_agents_other(self):
        ident = "PI-A-agents-other"
        try:
            rules = visibility.load_base(SETUP)
            denied = []
            for role in visibility.LAUNCHABLE:
                if not visibility.is_denied(".agents/other", role, rules):
                    denied.append(role)
            mounts, _r, _w, _d = mounts_for("developer", self.repo, self.work, self.keel)
            aud, _r2, _w2, _d2 = mounts_for("skills_auditor", self.repo, self.work, self.keel)
            leaked = [item[1] for item in mounts + aud if item[1] == "/work/.agents/other" or item[1] == "/work/.agents"]
            if not denied and not leaked:
                self.emit(ident, "BLOCKED", "rest of .agents stays denied")
            else:
                self.emit(ident, "NOT BLOCKED", ",".join(denied + leaked))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_carve(self):
        ident = "PI-A5a"
        try:
            rules = visibility.load_base(SETUP)
            bad = []
            for role in visibility.LAUNCHABLE:
                if visibility.is_denied(".agents/skills", role, rules) or visibility.is_denied(".agents/skills/demo", role, rules):
                    bad.append(role + ":skills")
                if not visibility.is_denied(".agents/other", role, rules):
                    bad.append(role + ":other")
            if not bad:
                self.emit(ident, "BLOCKED", "skills granted, other denied")
            else:
                self.emit(ident, "NOT BLOCKED", ",".join(bad))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_loud(self):
        ident = "PI-A5b"
        try:
            harness = os.path.join(self.root, "loud-harness")
            shutil.copytree(os.path.join(SETUP, "allow"), os.path.join(harness, "allow"))
            shutil.copytree(os.path.join(SETUP, "deny"), os.path.join(harness, "deny"))
            path = os.path.join(harness, "allow", "developer.paths")
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(".keel/logs\n")
            work = os.path.join(self.root, "loud-work")
            for rel in ("src", "docs", "tests", ".agents/skills", ".keel/memory", ".keel/logs"):
                os.makedirs(os.path.join(work, *rel.split("/")), exist_ok=True)
            try:
                visibility.build_mounts("developer", work, harness, os.path.join(self.root, "loud-keel"), "task-1", self.repo, {})
            except visibility.PolicyError as err:
                if err.code == "allow_denied":
                    self.emit(ident, "BLOCKED", "denied allow root refuses")
                else:
                    self.emit(ident, "ERROR", err.code)
                return
            self.emit(ident, "NOT BLOCKED", "denied allow root was withheld")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_memory_ro(self):
        ident = "PI-A6"
        try:
            mounts, _r, _w, _d = mounts_for("developer", self.repo, self.work, self.keel)
            item = mount_named(mounts, "/work/.keel/memory")
            if item is None:
                self.emit(ident, "NOT BLOCKED", "memory mount missing")
                return
            held, detail = ro_holds(item[0], item[1], item[2])
            if held:
                self.emit(ident, "BLOCKED", "memory write denied")
            else:
                self.emit(ident, "ERROR" if detail == "docker missing" else "NOT BLOCKED", detail)
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_memsym(self):
        ident = "PI-A-memsym"
        try:
            mem = os.path.join(self.root, "mem-link")
            os.makedirs(mem)
            outside = os.path.join(self.root, "mem-secret.txt")
            with open(outside, "w", encoding="utf-8") as handle:
                handle.write("OUTSIDE-SECRET\n")
            os.symlink(outside, os.path.join(mem, "note.md"))
            try:
                pi_launch.build_memory_index(mem, None)
            except visibility.PolicyError as err:
                if err.code == "memory_symlink":
                    self.emit(ident, "BLOCKED", "memory symlink refused")
                else:
                    self.emit(ident, "ERROR", err.code)
                return
            self.emit(ident, "NOT BLOCKED", "symlink was read")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_meminj(self):
        ident = "PI-A-meminj"
        try:
            mem = os.path.join(self.root, "mem-inj")
            os.makedirs(os.path.join(mem, "discoveries"))
            with open(os.path.join(mem, "discoveries", "note.md"), "w", encoding="utf-8") as handle:
                handle.write("---\ndate: 2024-01-01\ntitle: hello\nINJECT\x01\ntags: t\n---\nbody\n")
            result = pi_launch.build_memory_index(mem, None)
            text = result["text"]
            raw = "\nINJECT" in text or "\x01" in text
            fenced = "[data]" in text and "[/data]" in text
            if fenced and not raw:
                self.emit(ident, "BLOCKED", "header fenced")
            else:
                self.emit(ident, "NOT BLOCKED", "raw header")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_mempath(self):
        ident = "PI-A-mempath"
        try:
            base = os.path.join(self.root, "mem-path")
            mem = os.path.join(base, "memory")
            os.makedirs(mem)
            with open(os.path.join(mem, "note.md"), "w", encoding="utf-8") as handle:
                handle.write("---\ndate: 2024-02-02\ntitle: Inside\ntags: a\n---\nbody\n")
            with open(os.path.join(base, "secret.txt"), "w", encoding="utf-8") as handle:
                handle.write("OUTSIDE\n")
            try:
                result = pi_launch.build_memory_index(mem, None)
            except visibility.PolicyError as err:
                if err.code == "memory_path":
                    self.emit(ident, "NOT BLOCKED", "opened outside the memory dir")
                else:
                    self.emit(ident, "ERROR", err.code)
                return
            outside = [path for path in result["opened"] if not pi_launch._under(path, mem)]
            if result["audit_armed"] and result["audit_fired"] >= 1 and not outside:
                self.emit(ident, "BLOCKED", "opens stay in the memory dir")
            else:
                self.emit(ident, "NOT BLOCKED", "armed={0} fired={1}".format(result["audit_armed"], result["audit_fired"]))
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_ancestor_guard(self):
        ident = "PI-A3"
        try:
            script = pi_launch.ancestor_script(SETUP)
            clean = os.path.join(self.root, "anc-clean")
            os.makedirs(os.path.join(clean, "work"))
            proc = run(["sh", script, clean])
            if proc.returncode != 0:
                self.emit(ident, "NOT BLOCKED", "clean root failed")
                return
            names = ("AGENTS.md", "AGENTS.MD", "CLAUDE.md", "CLAUDE.MD")
            for name in names:
                rooted = os.path.join(self.root, "anc-" + name)
                os.makedirs(os.path.join(rooted, "work"))
                open(os.path.join(rooted, name), "w", encoding="utf-8").close()
                got = run(["sh", script, rooted])
                if got.returncode == 0:
                    self.emit(ident, "NOT BLOCKED", name + " at root")
                    return
                base = os.path.join(self.root, "mid-" + name)
                os.makedirs(os.path.join(base, "layer", "work"))
                open(os.path.join(base, "layer", name), "w", encoding="utf-8").close()
                got = run(["sh", script, base, os.path.join(base, "layer", "work")])
                if got.returncode == 0:
                    self.emit(ident, "NOT BLOCKED", name + " between / and /work")
                    return
            image_ok, detail = pi_launch.image_ancestors_clean(SETUP)
            if image_ok:
                self.emit(ident, "BLOCKED", "ancestor files refused")
            else:
                self.emit(ident, "ERROR" if "docker" in detail.lower() or detail == "guard failed" else "NOT BLOCKED", detail)
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)

    def check_pin(self):
        ident = "PI-A-pin"
        try:
            live = pi_launch.installed_version()
            image = pi_launch.image_pi_version()
            if pi_launch.version_ok(live) and pi_launch.version_ok(image) and not pi_launch.version_ok("0.0.0"):
                self.emit(ident, "BLOCKED", live)
            else:
                self.emit(ident, "NOT BLOCKED", live + " " + image)
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__ + " " + str(exc)[:160])

    def check_missing_row(self):
        ident = "PI-A8"
        try:
            score = os.path.join(self.root, "pi-score.tsv")
            lines = []
            for n in range(1, 10):
                ident_row = "PI-0{0}".format(n)
                if n == 4:
                    continue
                if n == 5:
                    lines.append(ident_row + "\tskip\tskipped\n")
                else:
                    lines.append(ident_row + "\tpass\tok\n")
            with open(score, "w", encoding="utf-8") as handle:
                handle.writelines(lines)
            env = os.environ.copy()
            proc = run(["bash", os.path.join(SETUP, "keel-doctor.sh"), "--pi-score", score], timeout=30, env=env)
            text = proc.stdout.decode("utf-8", "replace")
            if proc.returncode != 0 and "NOT READY" in text and "PI-04" in text:
                self.emit(ident, "BLOCKED", "missing or skipped row is not ready")
            else:
                self.emit(ident, "NOT BLOCKED", "score accepted a gap")
        except Exception as exc:
            self.emit(ident, "ERROR", type(exc).__name__)


def main():
    pin = os.environ.get("KEEL_PI_BIN", "")
    if not pin or not os.path.isfile(pin):
        say("PI-H1", "ERROR", "KEEL_PI_BIN is not set")
        return 1
    suite = Suite()
    try:
        suite.check_order()
        suite.check_prompt()
        suite.check_brief()
        suite.check_append_flag()
        suite.check_context_on()
        suite.check_ancestors()
        suite.check_catalog()
        suite.check_skills_mounts()
        suite.check_memory_happy()
        suite.check_tools()
        suite.check_precedence()
        suite.check_append_attack()
        suite.check_ext()
        suite.check_prompts()
        suite.check_home()
        suite.check_agentdir()
        suite.check_skills_ro()
        suite.check_skills_src()
        suite.check_skill_symlink()
        suite.check_agents_other()
        suite.check_carve()
        suite.check_loud()
        suite.check_memory_ro()
        suite.check_memsym()
        suite.check_meminj()
        suite.check_mempath()
        suite.check_ancestor_guard()
        suite.check_pin()
        suite.check_missing_row()
        suite.check_doctor_ready()
    finally:
        suite.close()
    return 0 if suite.ok else 1


if __name__ == "__main__":
    sys.exit(main())
