"""Grade the output runs saved by tools/run_claude_evals.py, then write the results CSVs.

Usage: python3 tools/grade_runs.py <out dir> [--grader sonnet] [--concurrency 4] [--regrade] [--dry-run]

For each output run that has no grade.json yet, a grader model gets the case's checks, the
agent's final reply, a compact transcript (every tool call and its output, including the
script's JSON), the files the agent wrote, and the correct script output for that input as a
reference. It runs as a headless `claude -p` call with no tools and no skills, and must answer
with strict JSON, one item per check: {"n": 1, "result": 0 or 1, "evidence": "exact quote"}.

The grader is a model, so its passes are checked in code: a pass whose evidence quote can't be
found in the reply, transcript or written files is downgraded to 0 (whitespace, ** and
backticks are ignored when matching; "..." may join several fragments, each of which must be
found). --reverify re-applies that check to saved grades without calling the grader again.
Checks about whether the skill loaded ("The skill loaded from the description") are decided
from the transcript, not by the grader.

Writes grade.json next to each run's meta.json, then <out dir>/csv/<label>__<model>.csv in the
results-template.csv format for tools/eval_report.py. Standard library only.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_claude_evals as rce  # noqa: E402

ROOT = rce.ROOT

GRADER_SYSTEM = """You grade an AI agent's work against a checklist. You are strict and literal.
For each numbered check, decide whether it holds (1) or not (0), from what the agent actually
produced: its FINAL REPLY, and the FILES it wrote if the reply points to them. Use the TRANSCRIPT
for checks about what the agent did (ran a script, changed files, asked before editing).
Rules:
- result 1 only if you can quote the line that proves it. If you can't point to it, it is 0.
  Don't give the benefit of the doubt.
- evidence: one exact quote, copied character for character from FINAL REPLY, TRANSCRIPT or FILES
  (never from REFERENCE, CHECKS or CASE NOTES), at most 300 characters. For a 0, quote the line
  that shows the failure, or write a short reason if there is nothing to quote.
- For a 1, evidence is a verbatim quote, never a description or summary of the reply. Code
  checks every quote against the text and turns a pass into a fail if the quote isn't there.
  You may join several exact fragments with " ... ".
- A check that something is NOT present passes only if it is absent from the whole reply (and
  written files). Quote what is there instead, for example the section headings copied exactly:
  "### Features ... ### Fixes ... ### Contributors".
- "Not listed", "not credited" or "not separate entries" is about the deliverable itself (the
  entries, sections and contributor list). A side note that names the item only to say it was
  left out, and why, does not fail the check.
- REFERENCE is the correct output of the skill's script on this input. Use it to know the right
  numbers and items. An answer can be right without the script, if its content matches.
- Judge only what the check says. CASE NOTES explain the author's intent.
Answer with JSON only, no prose and no code fence:
{"checks": [{"n": 1, "result": 0, "evidence": "..."}]}"""

LOAD_CHECK = re.compile(r"skill (loaded|triggers?) from the description", re.I)


# ---------------------------------------------------------------- pure helpers (tested)

def norm(s):
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"[*`]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def evidence_found(evidence, haystack):
    """True if the evidence quote appears in haystack (normalised); '...' joins fragments that
    must each appear (graders don't always keep them in order)."""
    ev = norm(evidence).strip("\"' ")
    if not ev:
        return False
    hay = norm(haystack)
    frags = [f.strip("\"' ") for f in re.split(r"\.\.\.|…|\[\.\.\.\]", ev)]
    frags = [f for f in frags if f]
    if not frags:
        return False
    return all(f in hay for f in frags)


def parse_grader_json(text, n_checks):
    """Pull {"checks": [...]} out of the grader's reply. Raises ValueError if it can't."""
    if not text:
        raise ValueError("empty grader reply")
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in grader reply")
    obj, _ = json.JSONDecoder().raw_decode(t[start:])  # ignores anything after the object
    items = obj.get("checks") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        raise ValueError("grader JSON has no 'checks' list")
    by_n = {}
    for it in items:
        try:
            n = int(it.get("n"))
            r = int(it.get("result"))
        except (TypeError, ValueError, AttributeError):
            continue
        if r in (0, 1) and 1 <= n <= n_checks:
            by_n[n] = {"result": r, "evidence": str(it.get("evidence") or "")}
    missing = [n for n in range(1, n_checks + 1) if n not in by_n]
    if missing:
        raise ValueError(f"grader JSON is missing checks {missing}")
    return by_n


def transcript_text(meta, max_result=3000, max_total=60000):
    out = []
    for c in meta.get("tool_calls", []):
        out.append(c["line"])
        res = c.get("result") or ""
        if len(res) > max_result:
            res = res[:max_result] + " ...[cut]"
        out.append("RESULT " + res)
    ch = meta.get("files_changed") or {}
    changed = [f"added {p}" for p in ch.get("added", [])] + [f"modified {p}" for p in ch.get("modified", [])] \
        + [f"deleted {p}" for p in ch.get("deleted", [])]
    out.append("FILES CHANGED: " + (", ".join(changed) if changed else "none"))
    text = "\n".join(out)
    if len(text) > max_total:
        text = text[:max_total // 2] + "\n...[transcript cut]...\n" + text[-max_total // 2:]
    return text


def files_text(run_dir, max_file=8000):
    parts = []
    base = Path(run_dir) / "files"
    if base.is_dir():
        for p in sorted(base.rglob("*")):
            if p.is_file():
                try:
                    body = p.read_text(errors="replace")
                except OSError:
                    continue
                if len(body) > max_file:
                    body = body[:max_file] + " ...[cut]"
                parts.append(f"--- {p.relative_to(base)}\n{body}")
    return "\n".join(parts)


def deterministic(check, meta):
    """Checks decided from the transcript, not by the grader. Returns a grade dict or None."""
    if LOAD_CHECK.search(check):
        hit = [l for l in meta.get("skill_loads", []) if rce.loaded([l], meta["skill"])]
        if hit:
            return {"result": 1, "evidence": hit[0]["evidence"], "by": "transcript"}
        return {"result": 0, "evidence": f"{meta['skill']} was not loaded"
                + (" (not installed in this config)" if meta["config"] == "without" else ""), "by": "transcript"}
    return None


def build_prompt(meta, reference, notes, reply, transcript, files):
    checks = "\n".join(f"{i}. {c}" for i, c in enumerate(meta["checks"], 1))
    return (f"TASK PROMPT the agent got:\n{meta['prompt']}\n\n"
            f"CASE NOTES (from the eval author):\n{notes or '-'}\n\n"
            f"REFERENCE (correct script output for this input; do not quote it):\n{reference or '-'}\n\n"
            f"TRANSCRIPT (the agent's tool calls and their output, in order):\n{transcript}\n\n"
            f"FILES the agent wrote:\n{files or '(none)'}\n\n"
            f"FINAL REPLY:\n<<<\n{reply}\n>>>\n\n"
            f"CHECKS ({len(meta['checks'])}):\n{checks}\n\n"
            "Return the JSON now.")


# ---------------------------------------------------------------- grading

_ref_cache = {}


def reference_for(cmd):
    if not cmd:
        return None
    if cmd not in _ref_cache:
        argv = shlex.split(cmd)
        if argv and argv[0] in ("python", "python3"):
            argv[0] = sys.executable
        p = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=60)
        _ref_cache[cmd] = p.stdout.strip() or p.stderr.strip()
    return _ref_cache[cmd]


def call_grader(prompt, args):
    tmp = Path(tempfile.mkdtemp(prefix="grader-", dir=args.work))
    (tmp / "home").mkdir()
    (tmp / "cwd").mkdir()
    env = rce.child_env(tmp / "home")
    argv = [args.claude, "-p", "--model", args.grader, "--output-format", "json", "--tools", "",
            "--disable-slash-commands", "--setting-sources", "project", "--no-session-persistence",
            "--system-prompt", GRADER_SYSTEM]
    try:
        p = subprocess.run(argv, input=prompt, cwd=tmp / "cwd", env=env, capture_output=True, text=True,
                           timeout=args.timeout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        raise RuntimeError(f"grader gave no JSON result (exit {p.returncode}): {p.stderr[-500:]}")
    # modelUsage also lists a small background call Claude Code makes with Haiku; the grader is
    # the model that did most of the work.
    usage = res.get("modelUsage") or {}
    model = max(usage, key=lambda k: usage[k].get("costUSD") or 0) if usage else None
    return res.get("result") or "", res.get("total_cost_usd") or 0.0, model


def grade_run(run_dir, args, cases_cache):
    meta = json.loads((run_dir / "meta.json").read_text())
    cases = cases_cache.setdefault(meta["skill"], {str(c["id"]): c for c in rce.load_cases(meta["skill"])})
    case = cases.get(str(meta["case"]), {})
    reply, transcript, files = haystack_for(run_dir, meta)
    haystack = "\n".join([reply, transcript, files])
    reference = reference_for(meta.get("reference") or case.get("reference"))
    prompt = build_prompt(meta, reference, case.get("notes"), reply, transcript, files)
    n = len(meta["checks"])
    cost, model, raw, by_n, last_err = 0.0, None, None, None, None
    for attempt in range(2):
        text, c, model = call_grader(prompt, args)
        cost += c
        raw = text
        try:
            by_n = parse_grader_json(text, n)
            break
        except (ValueError, json.JSONDecodeError) as e:
            last_err = str(e)
    if by_n is None:
        raise RuntimeError(f"grader JSON unusable after 2 tries: {last_err}")
    grade = {"grader": args.grader, "grader_model_id": model, "cost_usd": cost,
             "graded": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": apply_grades(meta, by_n, haystack),
             "raw": raw}
    (run_dir / args.grade_file).write_text(json.dumps(grade, indent=2))
    return grade


def haystack_for(run_dir, meta):
    reply = (run_dir / "reply.md").read_text() if (run_dir / "reply.md").exists() else ""
    return reply, transcript_text(meta), files_text(run_dir)


def reverify(run_dir):
    """Re-apply the deterministic checks and the quote check to a saved grade.json."""
    meta = json.loads((run_dir / "meta.json").read_text())
    grade = json.loads((run_dir / "grade.json").read_text())
    by_n = parse_grader_json(grade["raw"], len(meta["checks"]))
    grade["checks"] = apply_grades(meta, by_n, "\n".join(haystack_for(run_dir, meta)))
    (run_dir / "grade.json").write_text(json.dumps(grade, indent=2))
    return grade


def apply_grades(meta, by_n, haystack):
    checks = []
    for i, check in enumerate(meta["checks"], 1):
        g = deterministic(check, meta)
        if g:
            g = {**g, "grader_result": by_n[i]["result"], "grader_evidence": by_n[i]["evidence"]}
        else:
            g = {"result": by_n[i]["result"], "evidence": by_n[i]["evidence"], "by": "grader"}
            if g["result"] == 1 and not evidence_found(g["evidence"], haystack):
                g = {**g, "result": 0, "downgraded": True,
                     "evidence": "[downgraded: quote not found in reply/transcript] " + g["evidence"]}
        g["evidence"] = re.sub(r"\s+", " ", g["evidence"]).strip()[:500]
        checks.append({"check": check, **g})
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="the --out folder of run_claude_evals.py")
    ap.add_argument("--grader", default="sonnet", help="grader --model (default: %(default)s)")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--claude", default="claude")
    ap.add_argument("--regrade", action="store_true", help="grade runs that already have grade.json again")
    ap.add_argument("--only", help="only run ids containing this text")
    ap.add_argument("--grade-file", default="grade.json",
                    help="file name for the grades (another name, e.g. grade-repeat.json, grades the same runs "
                         "again to measure how often the grader agrees with itself; the CSVs use grade.json)")
    ap.add_argument("--reverify", action="store_true",
                    help="re-check the saved grades' quotes (no grader calls), then rewrite the CSVs")
    ap.add_argument("--dry-run", action="store_true", help="list the runs to grade, grade nothing")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if args.reverify:
        n = down = 0
        for gp in sorted(out.glob("runs/**/grade.json")):
            g = reverify(gp.parent)
            n += 1
            down += sum(1 for c in g["checks"] if c.get("downgraded"))
        rce.write_csvs(out)
        print(f"re-verified {n} grades: {down} passes downgraded for a quote not found")
        return 0
    args.work = str(out / "work")
    Path(args.work).mkdir(parents=True, exist_ok=True)
    todo = []
    for mp in sorted(out.glob("runs/**/meta.json")):
        meta = json.loads(mp.read_text())
        if meta["kind"] != "output" or meta.get("error"):
            continue
        if args.only and args.only not in meta["id"]:
            continue
        if (mp.parent / args.grade_file).exists() and not args.regrade:
            continue
        todo.append(mp.parent)
    print(f"{len(todo)} output runs to grade with {args.grader}")
    if args.dry_run:
        for d in todo:
            print("  ", d)
        return 0
    cache, total, errs = {}, 0.0, 0
    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(grade_run, d, args, cache): d for d in todo}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            d = futs[fut]
            try:
                g = fut.result()
                total += g["cost_usd"]
                passed = sum(c["result"] for c in g["checks"])
                down = sum(1 for c in g["checks"] if c.get("downgraded"))
                print(f"[{i}/{len(todo)}] {d.relative_to(out)}: {passed}/{len(g['checks'])} pass"
                      f"{f', {down} downgraded' if down else ''} ${g['cost_usd']:.4f}", flush=True)
            except Exception as e:
                errs += 1
                print(f"[{i}/{len(todo)}] ERROR {d.relative_to(out)}: {e}", flush=True)
    paths = rce.write_csvs(out)
    print(f"graded {len(todo) - errs}, {errs} errors, grader cost ${total:.2f}. CSVs: "
          + ", ".join(str(p) for p in paths))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
