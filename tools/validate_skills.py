"""Check every skill in skills/ against the Agent Skills format (agentskills.io/specification)
and this repo's safety rules. Standard library only.

Usage: python3 tools/validate_skills.py [skills_dir]
Exit code 1 if any skill has an error.
"""
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
KNOWN_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
RESERVED = ("anthropic", "claude")
MAX_BODY_LINES = 500  # Anthropic's authoring guide: keep the SKILL.md body under 500 lines
FILE_REF = re.compile(r"(?<![\w/.-])((?:scripts|references|templates|assets)/[\w./-]+\.\w+)")
RISKY = [
    (re.compile(r"/Users/|/home/[a-z]"), "absolute local path"),
    (re.compile(r"curl[^\n|]*\|\s*(sh|bash)\b|wget[^\n|]*\|\s*(sh|bash)\b"), "pipes a download into a shell"),
    (re.compile(r"\bbase64\s+(-d|--decode)\b"), "decodes base64 at run time"),
    (re.compile(r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY"), "looks like a secret"),
]


def frontmatter(text):
    """Return (fields, body). Supports simple `key: value` lines, which is all this repo uses."""
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with a '---' frontmatter line")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError("frontmatter is not closed with '---'")
    fields, key = {}, None
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            fields[key] = m.group(2).strip().strip('"').strip("'")
        elif key and line.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + line.strip()).strip()
        else:
            raise ValueError(f"can't read frontmatter line: {line!r}")
    return fields, text[end + 4:].lstrip("\n")


def check(skill_dir):
    errors, warnings = [], []
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return [f"{skill_dir.name}: missing SKILL.md"], []
    text = md.read_text(encoding="utf-8")
    try:
        fields, body = frontmatter(text)
    except ValueError as e:
        return [f"{skill_dir.name}: {e}"], []

    name, desc = fields.get("name", ""), fields.get("description", "")
    if not name:
        errors.append("missing name")
    elif len(name) > 64 or not NAME_RE.match(name):
        errors.append(f"name '{name}' must be 1-64 lowercase letters, digits and single hyphens")
    elif name != skill_dir.name:
        errors.append(f"name '{name}' must match the folder name '{skill_dir.name}'")
    if any(r in name for r in RESERVED):
        errors.append(f"name '{name}' uses a reserved word")
    if not desc:
        errors.append("missing description")
    elif len(desc) > 1024:
        errors.append(f"description is {len(desc)} characters (max 1024)")
    elif "<" in desc or ">" in desc:
        errors.append("description must not contain angle brackets")
    elif not re.search(r"\b(use|when)\b", desc, re.I):
        warnings.append("description should say when to use the skill ('Use when ...')")
    if len(fields.get("compatibility", "")) > 500:
        errors.append("compatibility is over 500 characters")
    for k in fields:
        if k not in KNOWN_KEYS:
            warnings.append(f"unknown frontmatter field '{k}'")

    n = len(body.splitlines())
    if n > MAX_BODY_LINES:
        errors.append(f"SKILL.md body is {n} lines (keep it under {MAX_BODY_LINES}; move detail to references/)")
    for ref in sorted(set(FILE_REF.findall(body))):
        if not (skill_dir / ref).is_file():
            errors.append(f"SKILL.md mentions {ref}, which doesn't exist")

    for f in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
        try:
            content = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            warnings.append(f"{f.relative_to(skill_dir)} is binary; review it by hand")
            continue
        for pat, why in RISKY:
            if pat.search(content):
                errors.append(f"{f.relative_to(skill_dir)}: {why}")
    return [f"{skill_dir.name}: {e}" for e in errors], [f"{skill_dir.name}: {w}" for w in warnings]


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "skills")
    skills = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    if not skills:
        print(f"no skills found in {root}")
        return 1
    all_errors = 0
    for s in skills:
        errs, warns = check(s)
        all_errors += len(errs)
        print(f"{'FAIL' if errs else 'ok  '}  {s.name}")
        for m in errs:
            print(f"      error: {m}")
        for m in warns:
            print(f"      warning: {m}")
    print(f"{len(skills)} skill(s), {all_errors} error(s)")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
