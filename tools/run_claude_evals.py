"""Run a skill's output evals and trigger tests with Claude Code in headless mode.

Every run is a fresh `claude -p` session in a fresh copy of a scratch project, so nothing
carries over between runs. Each run's full stream-json transcript, final reply and a
meta.json (skill loads, cost, duration, turns, files changed) are saved under --out.
Rows are written in the results-template.csv format, so tools/eval_report.py scores them.

Output evals (evals/<skill>/cases.json), with and without the skill:

  python3 tools/run_claude_evals.py --skill release-notes --models haiku,sonnet --runs 2

Test a different SKILL.md under the same name (for example the poor / good / great levels):

  python3 tools/run_claude_evals.py --skill release-notes --label release-notes-poor \\
      --skill-dir examples/poor-good-great/release-notes/poor --configs with --cases 1,3

Trigger tests (evals/<skill>/triggers.md). By default every skill in skills/ is installed
together, like a real library; --skill-dir installs only that folder instead:

  python3 tools/run_claude_evals.py --skill release-notes --triggers --runs 3

Then grade the output runs and write the CSVs:

  python3 tools/grade_runs.py <out dir>
  python3 tools/eval_report.py <out dir>/csv/<label>__<model>.csv

Use --dry-run first: it prints the plan and the number of runs. Runs whose meta.json
already exists are skipped, so an interrupted run picks up where it stopped.

Isolation. Claude Code also loads skills from your personal folders (~/.claude/skills) and
from plugins. This tool runs every session with HOME set to an empty scratch folder and
--setting-sources project, and unsets the env vars that sync skills into a session or add
your account's context to it (an attached claude.ai Project, your email), so the only skills it
sees are the ones copied into the scratch project plus Claude Code's built-in ones. Check the `skills` list in a run's meta.json to confirm. A baseline run can still find
the skill on disk (for example with `find / -name SKILL.md`). On Linux as root, --sandbox
runs each session in a private mount namespace that hides --hide paths (default: /home,
/tmp, ~/.claude, this repo and --out) and shows the project at /home/dev/project; use --keep
to put back a path the agent needs to log in. You still need to be logged in to Claude Code
(an API key in the environment, or your login kept with --keep).

Standard library only.
"""
import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLUMNS = ["kind", "model", "config", "case", "run", "check", "expected", "result", "evidence"]

# Env vars that pull the user's own skills, plugins, folders or session into a child session.
UNSET_ENV = [
    "CLAUDE_CODE_SYNC_SKILLS", "CCR_SKILL_OVERRIDES", "CLAUDE_ADDITIONAL_DIRECTORIES",
    "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", "CLAUDE_CODE_SYNC_PLUGINS",
    "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID",
    "CLAUDE_CODE_POST_TURN_MEMORY", "CLAUDE_CODE_POST_TURN_MEMORY_CONFIG",
    "CLAUDE_CODE_TEE_SDK_STDOUT", "CLAUDE_CODE_INCLUDE_PARTIAL_MESSAGES",
    # an attached claude.ai Project and the account email are added to the session's context
    "CLAUDE_PROJECT_UUID", "CLAUDE_PROJECT_TOOL", "CLAUDE_CODE_USER_EMAIL",
]
# Tools that reach outside the scratch project (publish, message, browse, schedule, spawn).
# The agent keeps Bash, Read, Write, Edit, Skill and the todo tools.
DISALLOWED_TOOLS = [
    "Artifact", "ArtifactComments", "ArtifactData", "Projects", "SendUserFile", "SendUserMessage",
    "PushNotification", "mcp__claude-in-chrome", "Task", "Workflow", "WebFetch", "WebSearch",
    "CronCreate", "CronDelete", "CronList", "ScheduleWakeup", "DesignSync", "ListAgents", "SendMessage",
    "ListConnectors", "ListPlugins", "ListSkills", "SearchMcpRegistry", "SearchPlugins", "SearchSkills",
    "ShowOnboardingRolePicker", "SuggestConnectors", "SuggestPluginInstall", "SuggestSkills",
    "ReadNotifications", "RefreshMcpTools", "EnterWorktree", "ExitWorktree", "Monitor", "ReportFindings",
]
SKIP_COPY = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "results")
CAGE_PROJECT = "/home/dev/project"
CAGE_HOME = "/home/dev"


# ---------------------------------------------------------------- parsing (tested)

def parse_triggers(text):
    """Parse a triggers.md: numbered items under '## Should trigger' and '## Should not trigger'.

    Returns [(case_id, query, expected)] with case ids S1.. and N1.., as in results-template.csv.
    """
    out, section, n = [], None, 0
    for line in text.splitlines():
        h = re.match(r"^##\s+(.*)", line)
        if h:
            title = h.group(1).lower()
            if title.startswith("should not trigger") or title.startswith("should not"):
                section, n = "N", 0
            elif title.startswith("should trigger"):
                section, n = "S", 0
            else:
                section = None
            continue
        m = re.match(r"^\s*\d+\.\s+(.*\S)\s*$", line)
        if section and m:
            n += 1
            out.append((f"{section}{n}", m.group(1), "fire" if section == "S" else "no-fire"))
    return out


def trigger_prompt(query):
    """The text sent to the agent: the query without a trailing '(annotation)' for the reader,
    e.g. 'Is this a good agent skill? (pastes a SKILL.md)' -> 'Is this a good agent skill?'."""
    return re.sub(r"\s*\([^()]*\)\s*$", "", query).strip() or query


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    parts.append(c.get("text", ""))
                elif c.get("type") == "image":
                    parts.append("[image]")
                else:
                    parts.append(json.dumps(c)[:2000])
            else:
                parts.append(str(c))
        return "\n".join(parts)
    return "" if content is None else str(content)


def parse_stream(lines):
    """Parse Claude Code stream-json lines into a summary dict."""
    s = {"model": None, "skills": [], "tools": [], "claude_code_version": None, "tool_calls": [],
         "reply": None, "assistant_text": [], "cost_usd": None, "duration_ms": None, "num_turns": None,
         "is_error": None, "subtype": None, "result_seen": False}
    by_id = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        if t == "system" and e.get("subtype") == "init":
            s["model"] = e.get("model")
            s["skills"] = e.get("skills") or []
            s["tools"] = e.get("tools") or []
            s["claude_code_version"] = e.get("claude_code_version")
        elif t == "assistant":
            for c in (e.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use":
                    call = {"id": c.get("id"), "name": c.get("name"), "input": c.get("input") or {},
                            "result": None, "parent": e.get("parent_tool_use_id")}
                    s["tool_calls"].append(call)
                    by_id[c.get("id")] = call
                elif c.get("type") == "text" and not e.get("parent_tool_use_id"):
                    s["assistant_text"].append(c.get("text", ""))
        elif t == "user":
            content = (e.get("message") or {}).get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id") in by_id:
                        by_id[c["tool_use_id"]]["result"] = _text_of(c.get("content"))
        elif t == "result":
            s["result_seen"] = True
            s["reply"] = e.get("result")
            s["cost_usd"] = e.get("total_cost_usd")
            s["duration_ms"] = e.get("duration_ms")
            s["num_turns"] = e.get("num_turns")
            s["is_error"] = e.get("is_error")
            s["subtype"] = e.get("subtype")
    if s["reply"] is None and s["assistant_text"]:
        s["reply"] = s["assistant_text"][-1]
    return s


def skill_loads(tool_calls):
    """Which skills were loaded: a Skill tool call, or reading .claude/skills/<name>/SKILL.md
    (with Read, or cat/head/sed/less in Bash). Returns [{"skill", "via", "evidence"}]."""
    loads = []
    pat = re.compile(r"\.claude/skills/([A-Za-z0-9_.:-]+)/SKILL\.md")
    for c in tool_calls:
        inp = c.get("input") or {}
        if c.get("name") == "Skill":
            name = str(inp.get("skill") or inp.get("command") or inp.get("name") or "").strip().lstrip("/")
            if name:
                loads.append({"skill": name, "via": "Skill", "evidence": tool_line(c)})
        elif c.get("name") == "Read":
            m = pat.search(str(inp.get("file_path", "")))
            if m:
                loads.append({"skill": m.group(1), "via": "Read", "evidence": tool_line(c)})
        elif c.get("name") == "Bash":
            cmd = str(inp.get("command", ""))
            if re.search(r"\b(cat|head|sed|less|more|tail)\b", cmd):
                for m in pat.finditer(cmd):
                    loads.append({"skill": m.group(1), "via": "Bash", "evidence": tool_line(c)})
    return loads


def loaded(loads, name):
    """True if the skill `name` (or 'plugin:name') is in loads."""
    return any(l["skill"] == name or l["skill"].split(":")[-1] == name for l in loads)


def tool_line(call, limit=600):
    """One line per tool call, the same text in meta.json, the grader's transcript and evidence."""
    inp = json.dumps(call.get("input") or {}, ensure_ascii=False, sort_keys=True)
    if len(inp) > limit:
        inp = inp[:limit] + " ...[cut]"
    return f"TOOL {call.get('name')} {inp}"


def checks_from_template(path):
    """{case: [check, ...]} from the output rows of a results-template.csv (config 'with')."""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["kind"] == "output" and r["config"] == "with":
                out.setdefault(str(r["case"]), []).append(r["check"])
    return out


def model_label(meta):
    lab = f"{meta.get('model_id') or meta['model']} / Claude Code {meta.get('claude_code_version') or ''}".strip()
    if meta.get("variant"):
        lab += f" / {meta['variant']}"
    return lab


def rows_for_meta(meta, grade=None):
    """CSV rows (results-template format) for one run."""
    model = model_label(meta)
    if meta["kind"] == "trigger":
        hit = loaded(meta.get("skill_loads", []), meta["skill"])
        ev = next((l["evidence"] for l in meta.get("skill_loads", []) if loaded([l], meta["skill"])), "")
        if not hit:
            others = sorted({l["skill"] for l in meta.get("skill_loads", [])})
            ev = "not loaded" + (f"; loaded instead: {', '.join(others)}" if others else "")
        if meta.get("error"):
            ev = f"run error: {meta['error']}"
        return [{"kind": "trigger", "model": model, "config": "with", "case": meta["case"], "run": meta["run"],
                 "check": meta["query"], "expected": meta["expected"],
                 "result": "" if meta.get("error") else int(hit), "evidence": ev}]
    rows = []
    graded = {g["check"]: g for g in (grade or {}).get("checks", [])}
    for check in meta["checks"]:
        g = graded.get(check)
        rows.append({"kind": "output", "model": model, "config": meta["config"], "case": meta["case"],
                     "run": meta["run"], "check": check, "expected": "pass",
                     "result": "" if g is None else g["result"],
                     "evidence": "" if g is None else g.get("evidence", "")})
    return rows


def write_csvs(out_dir, extra_rows_by_file=None):
    """Collect every run under out_dir into out_dir/csv/<label>__<model>.csv. Returns the paths."""
    out_dir = Path(out_dir)
    groups = {}
    for meta_path in sorted(out_dir.glob("runs/**/meta.json")):
        meta = json.loads(meta_path.read_text())
        grade_path = meta_path.parent / "grade.json"
        grade = json.loads(grade_path.read_text()) if grade_path.exists() else None
        key = (meta["label"], meta["model"])
        groups.setdefault(key, []).extend(rows_for_meta(meta, grade))
    paths = []
    (out_dir / "csv").mkdir(parents=True, exist_ok=True)
    for (label, model), rows in sorted(groups.items()):
        rows.sort(key=lambda r: (r["kind"] != "output", r["config"] != "without", _case_key(r["case"]),
                                 int(r["run"])))
        p = out_dir / "csv" / f"{label}__{model}.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
        paths.append(p)
    return paths


def _case_key(case):
    s = str(case)
    m = re.match(r"([A-Z]*)(\d+)", s)
    return (m.group(1), int(m.group(2))) if m else (s, 0)


# ---------------------------------------------------------------- planning

def load_cases(skill):
    p = ROOT / "evals" / skill / "cases.json"
    return json.loads(p.read_text())


def build_plan(args):
    plan = []
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    label = args.label or args.skill
    if args.triggers:
        queries = parse_triggers((ROOT / "evals" / args.skill / "triggers.md").read_text())
        if args.queries:
            want = set(args.queries.split(","))
            queries = [q for q in queries if q[0] in want]
        for model in models:
            for case, query, expected in queries:
                for run in range(1, args.runs + 1):
                    plan.append({"kind": "trigger", "label": label, "skill": args.skill, "model": model,
                                 "config": "with", "case": case, "run": run, "query": query,
                                 "prompt": trigger_prompt(query), "expected": expected, "files": [],
                                 "id": f"{label}/{model}/trigger/{case}-run{run}"})
        return plan
    cases = load_cases(args.skill)
    if args.cases:
        want = {int(c) for c in args.cases.split(",")}
        cases = [c for c in cases if c["id"] in want]
    configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    for model in models:
        for case in cases:
            for config in configs:
                for run in range(1, args.runs + 1):
                    plan.append({"kind": "output", "label": label, "skill": args.skill, "model": model,
                                 "config": config, "case": str(case["id"]), "run": run, "prompt": case["prompt"],
                                 "files": case.get("files", []), "checks": case["checks"],
                                 "reference": case.get("reference"),
                                 "id": f"{label}/{model}/{config}/case{case['id']}-run{run}"})
    return plan


def install_skills(args, project):
    """Copy the skill(s) for this run into project/.claude/skills/. Returns the names installed."""
    dest = project / ".claude" / "skills"
    dest.mkdir(parents=True, exist_ok=True)
    names = []
    if args.skill_dir:
        src = (ROOT / args.skill_dir) if not Path(args.skill_dir).is_absolute() else Path(args.skill_dir)
        target = dest / args.skill
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "SKILL.md", target / "SKILL.md")
        # Bring the real scripts/ and templates/ along so the steps' commands resolve.
        support = ROOT / "skills" / args.skill
        for sub in ("scripts", "templates", "references"):
            if (src / sub).is_dir():
                shutil.copytree(src / sub, target / sub, ignore=SKIP_COPY, dirs_exist_ok=True)
            elif (support / sub).is_dir():
                shutil.copytree(support / sub, target / sub, ignore=SKIP_COPY, dirs_exist_ok=True)
        # A SKILL.md that points at the script by its repo path (skills/<name>/scripts/...)
        # finds it there too.
        text = (src / "SKILL.md").read_text()
        if f"skills/{args.skill}/" in text:
            for sub in ("scripts", "templates"):
                if (support / sub).is_dir():
                    shutil.copytree(support / sub, project / "skills" / args.skill / sub,
                                    ignore=SKIP_COPY, dirs_exist_ok=True)
        names.append(args.skill)
    elif args.triggers and not args.only_target:
        for d in sorted((ROOT / "skills").iterdir()):
            if (d / "SKILL.md").exists():
                shutil.copytree(d, dest / d.name, ignore=SKIP_COPY)
                names.append(d.name)
    else:
        shutil.copytree(ROOT / "skills" / args.skill, dest / args.skill, ignore=SKIP_COPY)
        names.append(args.skill)
    return names


def place_files(files, project):
    for f in files:
        if isinstance(f, str):
            src, dst = ROOT / f, project / Path(f).name
        else:
            src, dst = ROOT / f["src"], project / f["dest"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=SKIP_COPY, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def snapshot(folder):
    out = {}
    for p in sorted(Path(folder).rglob("*")):
        if p.is_file() and not p.is_symlink():
            try:
                out[str(p.relative_to(folder))] = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                pass
    return out


def diff_snapshots(before, after):
    return {"added": sorted(set(after) - set(before)),
            "deleted": sorted(set(before) - set(after)),
            "modified": sorted(k for k in set(before) & set(after) if before[k] != after[k])}


def claude_argv(args, spec):
    argv = [args.claude, "-p", spec["prompt"], "--model", spec["model"], "--output-format", "stream-json",
            "--verbose", "--setting-sources", "project", "--dangerously-skip-permissions",
            "--disallowedTools", ",".join(DISALLOWED_TOOLS)]
    if spec["kind"] == "trigger":
        argv += ["--max-turns", str(args.max_turns)]
    return argv


def child_env(home):
    env = {k: v for k, v in os.environ.items() if k not in UNSET_ENV}
    env["HOME"] = str(home)
    return env


def sandbox_script(work, argv, hide, keep):
    """A sh script that, inside `unshare -m`, hides `hide` paths and runs argv in the cage."""
    cage = Path("/var/tmp/evalcage") / work.name
    lines = ["set -e", f"mkdir -p {shlex.quote(str(cage))}/run {shlex.quote(str(cage))}/home"]
    lines.append(f"mount --bind {shlex.quote(str(work / 'project'))} {shlex.quote(str(cage))}/run")
    lines.append(f"mount --bind {shlex.quote(str(work / 'home'))} {shlex.quote(str(cage))}/home")
    for i, k in enumerate(keep):
        lines.append(f"mkdir -p {shlex.quote(str(cage))}/keep{i}")
        lines.append(f"mount --bind {shlex.quote(k)} {shlex.quote(str(cage))}/keep{i}")
    for h in hide:
        lines.append(f"if [ -d {shlex.quote(h)} ]; then mount -t tmpfs none {shlex.quote(h)}; fi")
    for i, k in enumerate(keep):
        lines.append(f"mkdir -p {shlex.quote(k)}")
        lines.append(f"mount --bind {shlex.quote(str(cage))}/keep{i} {shlex.quote(k)}")
    lines.append(f"mkdir -p {CAGE_HOME}")
    lines.append(f"mount --bind {shlex.quote(str(cage))}/home {CAGE_HOME}")
    lines.append(f"mkdir -p {CAGE_PROJECT}")
    lines.append(f"mount --bind {shlex.quote(str(cage))}/run {CAGE_PROJECT}")
    lines.append("mount -t tmpfs none /var/tmp/evalcage")
    lines.append(f"cd {CAGE_PROJECT}")
    lines.append("exec " + " ".join(shlex.quote(a) for a in argv) + " < /dev/null")
    return "\n".join(lines)


# ---------------------------------------------------------------- execution

_lock = threading.Lock()


def run_one(args, spec, out_dir):
    run_dir = out_dir / "runs" / spec["id"]
    if (run_dir / "meta.json").exists():
        return "skipped", json.loads((run_dir / "meta.json").read_text())
    run_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9]+", "-", spec["id"]).strip("-")
    work = Path(args.work) / f"{safe}-{os.getpid()}-{int(time.time() * 1000) % 10**8}"
    if work.exists():
        shutil.rmtree(work)
    project, home = work / "project", work / "home"
    project.mkdir(parents=True)
    home.mkdir(parents=True)
    installed = install_skills(args, project) if spec["config"] == "with" else []
    place_files(spec.get("files", []), project)
    before = snapshot(project)
    argv = claude_argv(args, spec)
    t0 = time.time()
    err = None
    if args.sandbox:
        hide = list(args.hide or []) + [str(ROOT), str(out_dir.resolve()), str(Path(args.work).resolve())]
        script = sandbox_script(work, argv, hide, args.keep or [])
        env = child_env(CAGE_HOME)
        cmd, cwd = ["unshare", "-m", "--propagation", "private", "sh", "-c", script], "/"
    else:
        env = child_env(home)
        cmd, cwd = argv, str(project)
    with open(run_dir / "stream.jsonl", "w") as so, open(run_dir / "stderr.txt", "w") as se:
        try:
            p = subprocess.run(cmd, cwd=cwd, env=env, stdout=so, stderr=se, stdin=subprocess.DEVNULL,
                               timeout=args.timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc, err = None, f"timeout after {args.timeout}s"
    wall = time.time() - t0
    s = parse_stream(open(run_dir / "stream.jsonl").read().splitlines())
    if not s["result_seen"] and not err:
        err = f"no result event (exit {rc})"
    after = snapshot(project)
    changes = diff_snapshots(before, after)
    # keep a copy of every file the agent wrote, for the grader
    for rel in changes["added"] + changes["modified"]:
        src = project / rel
        if src.stat().st_size <= 200_000:
            dst = run_dir / "files" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    (run_dir / "reply.md").write_text(s["reply"] or "")
    meta = {k: v for k, v in spec.items() if k != "id"}
    meta.update({
        "id": spec["id"], "model_id": s["model"], "claude_code_version": s["claude_code_version"],
        "variant": args.variant, "skills_installed": installed, "skills_listed": s["skills"],
        "tools_listed": s["tools"], "skill_loads": skill_loads(s["tool_calls"]),
        "tool_calls": [{"line": tool_line(c), "result": (c["result"] or "")[:4000], "parent": c["parent"]}
                       for c in s["tool_calls"]],
        "cost_usd": s["cost_usd"], "duration_ms": s["duration_ms"], "wall_s": round(wall, 1),
        "num_turns": s["num_turns"], "subtype": s["subtype"], "is_error": s["is_error"], "exit_code": rc,
        "error": err, "files_changed": changes, "sandbox": bool(args.sandbox),
        "cwd": CAGE_PROJECT if args.sandbox else str(project),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t0)),
    })
    if spec["kind"] == "trigger":
        meta["target_loaded"] = loaded(meta["skill_loads"], spec["skill"])
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    if not args.keep_work:
        shutil.rmtree(work, ignore_errors=True)
    return ("error" if err else "ok"), meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skill", required=True, help="skill name: evals/<skill>/ holds cases.json and triggers.md")
    ap.add_argument("--skill-dir", help="install this folder's SKILL.md as the skill instead of skills/<skill>/ "
                    "(scripts/ and templates/ come from skills/<skill>/ if the folder has none)")
    ap.add_argument("--label", help="name for this experiment in paths and CSVs (default: the skill name)")
    ap.add_argument("--variant", help="added to the model column, e.g. 'release-notes:poor'")
    ap.add_argument("--models", default="haiku,sonnet,opus", help="comma-separated --model values (default: %(default)s)")
    ap.add_argument("--configs", default="without,with", help="output evals: without,with (default: %(default)s)")
    ap.add_argument("--cases", help="output evals: comma-separated case ids (default: all)")
    ap.add_argument("--runs", type=int, default=2, help="runs per prompt (default: %(default)s)")
    ap.add_argument("--triggers", action="store_true", help="run the trigger queries in triggers.md instead")
    ap.add_argument("--queries", help="triggers: comma-separated ids to run, e.g. S1,N3 (default: all)")
    ap.add_argument("--only-target", action="store_true",
                    help="triggers: install only this skill (default: every skill in skills/ together)")
    ap.add_argument("--max-turns", type=int, default=3, help="triggers: --max-turns per session (default: %(default)s)")
    ap.add_argument("--concurrency", type=int, default=3, help="sessions at once (default: %(default)s)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds before a session is killed (default: %(default)s)")
    ap.add_argument("--out", default="eval-runs", help="results folder (default: %(default)s)")
    ap.add_argument("--work", help="scratch folder for the per-run projects (default: <out>/work)")
    ap.add_argument("--keep-work", action="store_true", help="don't delete each run's scratch project")
    ap.add_argument("--claude", default="claude", help="the Claude Code binary (default: %(default)s)")
    ap.add_argument("--sandbox", action="store_true", help="Linux + root: run each session in a mount namespace "
                    "that hides --hide paths, so a baseline run can't find the skill on disk")
    ap.add_argument("--hide", action="append", help="sandbox: path to hide (repeatable; default /home /tmp ~/.claude)")
    ap.add_argument("--keep", action="append", help="sandbox: path inside a hidden one to put back (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the run count, run nothing")
    args = ap.parse_args(argv)

    if args.sandbox and not args.hide:
        args.hide = ["/home", "/tmp", str(Path.home() / ".claude")]
    out_dir = Path(args.out)
    args.work = args.work or str(out_dir / "work")
    plan = build_plan(args)
    todo = [s for s in plan if not (out_dir / "runs" / s["id"] / "meta.json").exists()]
    print(f"{len(plan)} runs planned, {len(plan) - len(todo)} already done, {len(todo)} to run "
          f"({'triggers' if args.triggers else 'output evals'}, label {args.label or args.skill}, "
          f"models {args.models}, concurrency {args.concurrency})")
    if args.dry_run:
        for s in plan[:400]:
            mark = "done" if s not in todo else "todo"
            print(f"  [{mark}] {s['id']}: {s['prompt'][:90]}")
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    Path(args.work).mkdir(parents=True, exist_ok=True)
    total_cost, n_done, n_err = 0.0, 0, 0
    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(run_one, args, s, out_dir): s for s in todo}
        for fut in cf.as_completed(futs):
            s = futs[fut]
            try:
                status, meta = fut.result()
            except Exception as e:  # keep going; the run has no meta.json and is retried next time
                status, meta = "crash", {"error": repr(e)}
            n_done += 1
            n_err += status in ("error", "crash")
            total_cost += meta.get("cost_usd") or 0
            extra = ""
            if s["kind"] == "trigger" and status == "ok":
                extra = f" loaded={int(meta['target_loaded'])} ({s['expected']})"
            elif status == "ok":
                extra = f" loads={[l['skill'] for l in meta['skill_loads']]}"
            with _lock:
                print(f"[{n_done}/{len(todo)}] {status} {s['id']} ${meta.get('cost_usd') or 0:.4f} "
                      f"{meta.get('wall_s', '?')}s{extra} {meta.get('error') or ''}", flush=True)
    paths = write_csvs(out_dir)
    print(f"done: {n_done} runs, {n_err} errors, ${total_cost:.2f} this session. CSVs: "
          + ", ".join(str(p) for p in paths))
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
