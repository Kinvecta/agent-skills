"""Mechanical checks for one Agent Skill folder, scored against the poor / good / great rubric.

Usage:
  python3 lint_skill.py path/to/skill-folder          readable report
  python3 lint_skill.py path/to/skill-folder --json   JSON on stdout

Each finding has: check, tier (the rubric level it belongs to: poor, good or great),
status (pass, check or fail), points, max_points, message and, where it helps, line.
These are heuristics. A "check" means a person or the model should look; it is not a verdict.
Reads only; writes nothing. Exit code 0 when the report ran, 1 when the folder can't be read.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Same safety patterns as tools/validate_skills.py (a test keeps them in sync). Some are
# split with [] so this file doesn't trip its own check.
RISKY = [
    (re.compile(r"/User[s]/|/home/[a-z]"), "absolute local path"),
    (re.compile(r"curl[^\n|]*\|\s*(sh|bash)\b|wget[^\n|]*\|\s*(sh|bash)\b"), "pipes a download into a shell"),
    (re.compile(r"\bbase64\s+(-d|--decode)\b"), "decodes base64 at run time"),
    (re.compile(r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY"),
     "looks like a secret"),
]
FILE_REF = re.compile(r"(?<![\w/.-])((?:scripts|references|templates|assets)/[\w./-]+\.\w+)")
WHEN = re.compile(r"\buse\b[^.]{0,40}\bwhen\b|\bwhen (the )?(user|you|someone|asked)\b|\buse (it |this )?(for|if)\b"
                  r"|\btriggers? (on|when)\b", re.I)
SEQUENCE = re.compile(r"\b(then|first|next|finally|afterwards|step \d|steps)\b", re.I)
VERB_LIST = re.compile(r"(?:^|,\s*|\bthen\s+|\band\s+)([a-z]+(?:es|s))\b")
BAD_START = re.compile(r"^(this skill|a skill|skill (for|to)|i |i'm|you |we )", re.I)
CAPS = re.compile(r"\b(MUST|NEVER|ALWAYS)\b")
BUFFET = re.compile(r"\b(use|using|try|choose|pick|either|options are|can use)\b[^.\n]{0,60}?"
                    r"(?:[\w.+-]+,\s+){2,}(?:and |or )?[\w.+-]+", re.I)
TIME = re.compile(r"\b(before|after|until|since) (19|20)\d\d\b|\bas of\b|\bcurrently\b|\bright now\b|\bthese days\b"
                  r"|\bthe latest version\b", re.I)
WIN_ABS = re.compile(r"\b[A-Z]:\\\\?[\w]")
BACKSLASH = re.compile(r"\b[\w.-]+\\[\w.-]+\.\w{1,4}\b")
GOTCHAS = re.compile(r"^#{1,4}\s*(gotchas|pitfalls|common mistakes|known issues|traps|watch out)\b", re.I)
BOUNDARY = re.compile(r"\b(not for|don't use|do not use|when not to use|not when|out of scope)\b", re.I)
VERIFY = re.compile(r"\b(check before|verify|validate|validation|checklist|self-check|check that|"
                    r"check each|check again)\b|^\s*[-*] \[ \]", re.I | re.M)


def frontmatter(text):
    """Return (fields, body, offset): body line i (0-based) is file line i + offset + 1."""
    all_lines = text.splitlines()
    if not all_lines or all_lines[0].strip() != "---":
        return {}, text, 0
    end = next((j for j in range(1, len(all_lines)) if all_lines[j].strip() == "---"), None)
    if end is None:
        return {}, text, 0
    fields, key = {}, None
    for line in all_lines[1:end]:
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            value = m.group(2).strip()
            fields[key] = "" if re.fullmatch(r"[>|][+-]?", value) else value.strip('"').strip("'")
        elif key and line.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + line.strip()).strip()
    start = end + 1
    while start < len(all_lines) and not all_lines[start].strip():
        start += 1
    return fields, "\n".join(all_lines[start:]), start


def find_evals(skill_dir, name):
    for p in ("evals", "tests", "evals.md"):
        if (skill_dir / p).exists():
            return f"{p} in the skill folder"
    if any(skill_dir.rglob("test_*.py")):
        return "test_*.py in the skill folder"
    # Repo layout used here: <repo>/skills/<name>/ with tests in <repo>/evals/<name>/
    skill_dir = skill_dir.resolve()
    if skill_dir.parent.name == "skills" and (skill_dir.parent.parent / "evals" / name).is_dir():
        return f"evals/{name}/ in the repo"
    return None


def lint(skill_dir):
    md = skill_dir / "SKILL.md"
    text = md.read_text(encoding="utf-8-sig")  # UnicodeDecodeError is handled in main()
    fields, body, off = frontmatter(text)
    name, desc = fields.get("name", skill_dir.name), fields.get("description", "")
    lines = body.splitlines()
    findings = []

    def add(check, tier, status, pts, max_pts, msg, line=None):
        f = {"check": check, "tier": tier, "status": status, "points": pts, "max_points": max_pts, "message": msg}
        if line:
            f["line"] = line
        findings.append(f)

    # 1. The trigger
    m = WHEN.search(desc)
    if m:
        add("when-clause", "poor", "pass", 2, 2, "description says when to use it")
    else:
        add("when-clause", "poor", "fail", 0, 2, "description has no 'Use when ...' clause, so the agent can't tell "
            "when to load it")
    what = desc[:m.start()] if m else desc
    if not desc:
        add("description", "poor", "fail", 0, 1, "no description")
    elif len(desc) < 40:
        add("description", "poor", "fail", 0, 1, f"description is {len(desc)} characters: too short to say what and when")
    elif len(desc) > 1024:
        add("description", "poor", "fail", 0, 1, f"description is {len(desc)} characters (spec max 1024)")
    elif BAD_START.match(desc):
        add("description", "good", "check", 0.5, 1, "description should start with what the skill does, in the third "
            "person ('Drafts ...'), not 'This skill' or 'I/You'")
    elif len(desc) > 600:
        add("description", "good", "check", 0.5, 1, f"description is {len(desc)} characters; put the key use case "
            "first (Claude Code cuts the listing at 1,536)")
    else:
        add("description", "good", "pass", 1, 1, f"description is {len(desc)} characters and leads with the job")
    seq = SEQUENCE.search(what)
    verbs = VERB_LIST.findall(what.lower())
    if seq:
        add("description-not-steps", "good", "fail", 0, 0.5, f"description uses '{seq.group(0)}': it may summarize "
            "the steps, and the agent can follow the summary instead of the body")
    elif len(verbs) >= 3:
        add("description-not-steps", "good", "check", 0.25, 0.5, f"description lists {len(verbs)} actions "
            f"({', '.join(verbs[:4])}); check it says what and when, not how")
    else:
        add("description-not-steps", "good", "pass", 0.5, 0.5, "description doesn't summarize the steps")

    # 2. Length
    n = len(lines)
    if n > 500:
        add("body-length", "poor", "fail", 0, 0.5, f"body is {n} lines (keep it under 500; move detail to references/)")
    elif n > 150:
        add("body-length", "good", "check", 0.25, 0.5, f"body is {n} lines; check every line earns its place")
    else:
        add("body-length", "good", "pass", 0.5, 0.5, f"body is {n} line{'s' if n != 1 else ''}")

    # 3. Hygiene: 5 checks at 0.2 each
    caps = [(i + off + 1, c) for i, l in enumerate(lines) for c in CAPS.findall(l)]
    if len(caps) >= 3:
        add("all-caps", "good", "check", 0, 0.2, f"{len(caps)} all-caps MUST/NEVER/ALWAYS: a yellow flag; explain "
            "why instead, or move a must-hold rule into a hook", caps[0][0])
    else:
        add("all-caps", "good", "pass", 0.2, 0.2, f"{len(caps)} all-caps MUST/NEVER/ALWAYS")
    buffets = [i + off + 1 for i, l in enumerate(lines) if BUFFET.search(l) and " or " in l]
    if buffets:
        add("option-buffet", "good", "check", 0, 0.2, f"{len(buffets)} line(s) offer 3+ alternatives; pick a default "
            "and name one escape hatch", buffets[0])
    else:
        add("option-buffet", "good", "pass", 0.2, 0.2, "no option buffets")
    refs = set(FILE_REF.findall(body))
    missing = sorted(r for r in refs if not (skill_dir / r).is_file())
    files = sorted(p.relative_to(skill_dir).as_posix() for p in skill_dir.rglob("*")
                   if p.is_file() and p.name != "SKILL.md" and "__pycache__" not in p.parts)
    unref = [f for f in files if f not in refs and f.split("/")[0] in ("scripts", "references", "templates", "assets")]
    nested = []
    for f in files:
        if f.startswith("references/") and f.endswith(".md"):
            inner = set(FILE_REF.findall((skill_dir / f).read_text(encoding="utf-8", errors="replace")))
            nested += [f"{f} -> {r}" for r in inner if r not in refs]
    if missing:
        add("references", "poor", "fail", 0, 0.2, f"SKILL.md mentions files that don't exist: {', '.join(missing)}")
    elif unref or nested:
        msg = []
        if unref:
            msg.append(f"not mentioned in SKILL.md, so the agent may never open: {', '.join(unref)}")
        if nested:
            msg.append(f"more than one level deep: {', '.join(nested)}")
        add("references", "good", "check", 0.1, 0.2, "; ".join(msg))
    else:
        add("references", "good", "pass", 0.2, 0.2, f"{len(refs)} file reference(s), all one level deep and present")
    t = [i + off + 1 for i, l in enumerate(lines) if TIME.search(l)]
    if t:
        add("time-sensitive", "good", "check", 0, 0.2, f"{len(t)} time-sensitive phrase(s) ('as of', 'currently', "
            "'before 2025'); these go stale", t[0])
    else:
        add("time-sensitive", "good", "pass", 0.2, 0.2, "no time-sensitive phrases")
    risky, port = [], []
    for p in [md] + [skill_dir / f for f in files]:
        try:
            content = p.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            continue
        rel = p.relative_to(skill_dir).as_posix()
        risky += [f"{rel}: {why}" for pat, why in RISKY if pat.search(content)]
        if p.suffix == ".md" and (WIN_ABS.search(content) or BACKSLASH.search(content)):
            port.append(rel)
    if risky:
        add("safety", "poor", "fail", 0, 0.2, "risky patterns: " + "; ".join(risky))
    elif port:
        add("safety", "good", "check", 0.1, 0.2, f"backslash or drive-letter paths in {', '.join(port)}; use forward "
            "slashes and paths relative to the skill")
    else:
        add("safety", "good", "pass", 0.2, 0.2, "no risky patterns, absolute paths or backslash paths")

    # 4. What makes it great
    g = next((i for i, l in enumerate(lines) if GOTCHAS.match(l)), None)
    if g is None:
        add("gotchas", "great", "fail", 0, 1.5, "no Gotchas section: the concrete traps from real failures are the "
            "highest-value content")
    else:
        items = 0
        for l in lines[g + 1:]:
            if l.startswith("#"):
                break
            items += bool(re.match(r"^\s*[-*\d]", l))
        if g > 100:
            add("gotchas", "great", "check", 1, 1.5, f"Gotchas start {g + 1} lines into the body; move them near the top "
                "(Claude Code keeps only the start of a skill after compaction)", g + off + 1)
        else:
            add("gotchas", "great", "pass", 1.5, 1.5, f"Gotchas section with {items} item(s); judge whether "
                "they're specific", g + off + 1)
    b = BOUNDARY.search(desc + "\n" + body)
    if b:
        add("boundary", "great", "pass", 1, 1, f"says where it stops ('{b.group(0)}')")
    else:
        add("boundary", "great", "fail", 0, 1, "no 'Not for' / 'Don't use' line: say what it doesn't handle and the "
            "simpler fallback")
    v = VERIFY.search(body)
    if v:
        add("verification", "good", "pass", 1.5, 1.5, f"has a check step ('{v.group(0).strip()}')")
    else:
        add("verification", "good", "fail", 0, 1.5, "no check-before-you-answer step: add validate, fix, repeat")
    e = find_evals(skill_dir, name)
    if e:
        add("evals", "great", "pass", 1, 1, f"tests found: {e}")
    else:
        add("evals", "great", "fail", 0, 1, "no evals found (evals/<name>/ in the repo, or tests in the folder): "
            "run it with and without the skill, plus should-trigger and near-miss prompts")

    score = round(sum(f["points"] for f in findings), 2)
    if risky:
        score = min(score, 3.0)
    level = "great" if score >= 8.5 else "good" if score >= 5 else "poor"
    return {"skill": name, "path": str(skill_dir), "score": score, "max": 10, "level": level,
            "body_lines": n, "description_chars": len(desc), "findings": findings}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("skill_dir", help="folder that holds SKILL.md")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a readable report")
    a = ap.parse_args()
    d = Path(a.skill_dir)
    if not (d / "SKILL.md").is_file():
        print(f"no SKILL.md in {d}", file=sys.stderr)
        return 1
    try:
        r = lint(d)
    except UnicodeDecodeError as e:
        print(f"can't read {d / 'SKILL.md'}: not UTF-8 text (byte {e.start})", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"can't read {d}: {e.strerror}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(r, indent=2))
        return 0
    print(f"{r['skill']}: {r['score']}/10 ({r['level']})")
    for f in r["findings"]:
        where = f" (line {f['line']})" if "line" in f else ""
        print(f"  {f['status']:<5} [{f['tier']}] {f['check']}: {f['message']}{where}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
