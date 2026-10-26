"""Group a git log export into release-note sections.

Usage:
  python3 group_changes.py changes.txt --version 1.4.0
  git log v1.3.0..v1.4.0 | python3 group_changes.py - --version 1.4.0

Input: plain `git log` output (commit / Author / Date / indented message), or one change
per line (`git log --oneline`, or a pasted list of merged PR titles).
Output: JSON on stdout with breaking, features, fixes, other, reverted, dropped,
contributors and problems. Diagnostics go to stderr. Reads only; writes nothing.
Exit code 0 when the JSON was printed (check "problems"), 1 when the input can't be read,
2 for bad arguments. Reverts pair with the nearest older match, assuming git's newest-first order.
"""
import argparse
import json
import re
import sys

COMMIT_RE = re.compile(r"^commit ([0-9a-f]{7,40})\b")
AUTHOR_RE = re.compile(r"^Author:\s*(.*?)\s*(<[^>]*>)?\s*$")
ONELINE_RE = re.compile(r"^(?:[-*]\s+)?(?:([0-9a-f]{7,40})\s+)?(.+)$")
SUBJECT_RE = re.compile(r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^()]+)\))?(?P<bang>!)?:\s*(?P<desc>\S.*)$")
PR_RE = re.compile(r"\s*\(#(\d+)\)\s*$")
BREAKING_RE = re.compile(r"^BREAKING[ -]CHANGE:\s*(.+)$")
REVERT_GIT_RE = re.compile(r'^Revert "(.+)"$')
REAPPLY_GIT_RE = re.compile(r'^Reapply "(.+)"$')  # newer git titles a revert of a revert this way
HEADER_RE = re.compile(r"^(AuthorDate|Commit|CommitDate|Date|Merge|Reflog|Reflog message):")
REVERTS_HASH_RE = re.compile(r"This reverts commit ([0-9a-f]{7,40})")
FOOTER_RE = re.compile(r"^([\w-]+|BREAKING CHANGE): ")
VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][\w.-]+)?$")

GROUPS = {"feat": "features", "fix": "fixes", "perf": "other", "refactor": "other",
          "docs": "other", "revert": "other"}
NOISE = {"chore", "ci", "build", "test", "style"}  # internal work; not user-facing
BOTS = re.compile(r"\[bot\]|dependabot|renovate|github-actions", re.I)


def read_commits(lines):
    """Yield dicts with line, hash, author, subject, body (list of lines)."""
    if any(COMMIT_RE.match(l) for l in lines):
        cur = None
        for n, line in enumerate(lines, start=1):
            m = COMMIT_RE.match(line)
            if m:
                if cur:
                    yield cur
                cur = {"line": n, "hash": m.group(1)[:7], "author": None, "subject": None, "body": []}
                continue
            if cur is None:
                continue
            a = AUTHOR_RE.match(line)
            if a and cur["subject"] is None and cur["author"] is None:
                cur["author"] = a.group(1)
            elif HEADER_RE.match(line) and cur["subject"] is None:
                continue  # Date:, Merge:, and the extra headers of --format=fuller
            elif line.strip():
                text = line.strip()
                if cur["subject"] is None:
                    cur["subject"], cur["line"] = text, n
                else:
                    cur["body"].append(text)
            elif cur["subject"] is not None:
                cur["body"].append("")  # keep paragraph breaks so footers end where they should
        if cur:
            yield cur
    else:
        for n, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            m = ONELINE_RE.match(line.strip())
            yield {"line": n, "hash": (m.group(1) or "")[:7] or None, "author": None,
                   "subject": m.group(2).strip(), "body": []}


def breaking_note(body):
    """The text of a BREAKING CHANGE footer, joined across lines until a blank line or the next footer."""
    for i, line in enumerate(body):
        m = BREAKING_RE.match(line)
        if m:
            parts = [m.group(1)]
            for nxt in body[i + 1:]:
                if not nxt or FOOTER_RE.match(nxt):
                    break
                parts.append(nxt)
            return " ".join(parts)
    return None


def conventional(subj):
    """Rewrite git's default titles, Revert "x" and Reapply "x", as conventional revert subjects."""
    rv = REVERT_GIT_RE.match(subj)
    if rv:
        return "revert: " + rv.group(1)
    ra = REAPPLY_GIT_RE.match(subj)
    if ra:  # reapplying x is reverting the revert of x
        return "revert: revert: " + ra.group(1)
    return subj


def key(e):
    return ((e["scope"] or "").lower(), e["type"], PR_RE.sub("", e["description"]).strip().lower())


def revert_target(desc):
    """The (scope, type, description) key a revert's description points at, or None."""
    inner = SUBJECT_RE.match(conventional(PR_RE.sub("", desc).strip()))
    if not inner:
        return None
    return ((inner.group("scope") or "").lower(), inner.group("type").lower(),
            PR_RE.sub("", inner.group("desc")).strip().lower())


def depth(desc):
    """How many reverts deep a revert is: 1 for a revert, 2 for a revert of a revert."""
    want = revert_target(desc)
    n = 1
    while want and want[1] == "revert":
        n += 1
        want = revert_target(conventional(want[2]))
    return n


def parse(c, problems, dropped):
    subj = c["subject"] or ""
    if subj.startswith(("Merge pull request", "Merge branch", "Merge remote-tracking")):
        dropped["merge"] = dropped.get("merge", 0) + 1
        return None
    if c["author"] and BOTS.search(c["author"]):  # bot commits are never user-facing entries
        label = "deps" if re.search(r"\(deps\)|^bump |dependenc", subj, re.I) else "bot"
        dropped[label] = dropped.get(label, 0) + 1
        return None
    pr = None
    m = PR_RE.search(subj)
    if m:
        pr, subj = int(m.group(1)), subj[:m.start()]
    subj = conventional(subj)
    m = SUBJECT_RE.match(subj)
    if not m:
        problems.append(f"line {c['line']}: no conventional type, left out: {c['subject']!r}")
        return None
    kind = m.group("type").lower()
    if kind in NOISE:
        label = "deps" if (m.group("scope") or "").lower() == "deps" else kind
        dropped[label] = dropped.get(label, 0) + 1
        return None
    if kind not in GROUPS:
        problems.append(f"line {c['line']}: unknown type '{kind}', left out: {c['subject']!r}")
        return None
    note = breaking_note(c["body"])
    reverts = next((r.group(1)[:7] for r in map(REVERTS_HASH_RE.search, c["body"]) if r), None)
    return {"type": kind, "scope": m.group("scope"), "description": m.group("desc").strip(),
            "pr": pr, "hash": c["hash"], "author": c["author"], "line": c["line"],
            "breaking": bool(m.group("bang") or note), "breaking_note": note, "reverts_hash": reverts}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", help="git log export file, or - for stdin")
    ap.add_argument("--version", required=True, help="the release version, e.g. 1.4.0 (must match the tag)")
    a = ap.parse_args()
    if not VERSION_RE.match(a.version):
        print(f"--version must look like 1.4.0 or v1.4.0, got {a.version!r}", file=sys.stderr)
        return 2
    try:
        if a.log == "-":
            data = sys.stdin.buffer.read()
        else:
            with open(a.log, "rb") as f:
                data = f.read()
        text = data.decode("utf-8-sig")
    except OSError as e:
        print(f"can't read {a.log}: {e.strerror}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as e:
        print(f"can't read {a.log}: not UTF-8 text (byte {e.start}); "
              "export it again with `git log > changes.txt`", file=sys.stderr)
        return 1

    problems, dropped = [], {}
    entries = [e for e in (parse(c, problems, dropped) for c in read_commits(text.splitlines())) if e]

    if not entries and not problems and not dropped:
        problems.append("no changes found in the input; check the file is a git log export or a list of changes")

    # A revert cancels the entry it reverts: matched by the hash in "This reverts commit", else by
    # type/scope/description, preferring the nearest older entry (git log lists newest first, so
    # older is further down). Reverts of reverts go first, so a reapplied change ships.
    reverted, cancelled = [], set()
    pos = {id(e): i for i, e in enumerate(entries)}
    reverts = [e for e in entries if e["type"] == "revert"]
    for r in sorted(reverts, key=lambda e: -depth(e["description"])):
        if id(r) in cancelled:
            continue
        want, here = revert_target(r["description"]), pos[id(r)]
        live = [e for e in entries if e is not r and id(e) not in cancelled]
        by_hash = [e for e in live if r["reverts_hash"] and e["hash"] == r["reverts_hash"]]
        by_key = [e for e in live if want and key(e) == want]
        older = sorted((e for e in by_key if pos[id(e)] > here), key=lambda e: pos[id(e)])
        newer = sorted((e for e in by_key if pos[id(e)] < here), key=lambda e: -pos[id(e)])
        target = (by_hash + older + newer or [None])[0]
        if target:
            cancelled.update({id(target), id(r)})
            if target["type"] != "revert":  # a reverted revert just means the original ships
                reverted.append({"description": target["description"], "pr": target["pr"],
                                 "hash": target["hash"], "reverted_by": r["hash"]})
        else:
            problems.append(f"line {r['line']}: revert of a change not in this range; "
                            f"it may undo something already released: {r['description']!r}")
    entries = [e for e in entries if id(e) not in cancelled]

    out = {"version": a.version.lstrip("v"), "breaking": [], "features": [], "fixes": [], "other": []}
    for e in entries:
        group = "breaking" if e["breaking"] else GROUPS[e["type"]]
        out[group].append({k: e[k] for k in ("type", "scope", "description", "pr", "hash", "author", "breaking_note")})
        if e["breaking"] and not e["breaking_note"]:
            problems.append(f"line {e['line']}: breaking change with no migration note: {e['description']!r}")
    out["counts"] = {g: len(out[g]) for g in ("breaking", "features", "fixes", "other")}
    out["reverted"] = reverted
    out["dropped"] = dict(sorted(dropped.items()))
    authors = {e["author"] for e in entries if e["author"]}
    out["contributors"] = sorted(x for x in authors if not BOTS.search(x))
    out["problems"] = problems
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
