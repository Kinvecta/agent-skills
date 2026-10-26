"""Score a skill's eval results: with vs without the skill, per check, and trigger tests.

Usage: python3 tools/eval_report.py <results.csv> [more.csv ...] [--json]

Each CSV uses the columns of evals/<skill>/results-template.csv:
  kind      output | trigger
  model     the model (and agent) you ran, e.g. "claude-sonnet / Claude Code"
  config    without | with   (trigger rows: with)
  case      output: the case number from evals.md; trigger: S1..S10 (should) or N1..N10 (near-miss)
  run       1, 2, 3 ...
  check     output: one check from evals.md; trigger: the query
  expected  output: pass; trigger: fire | no-fire
  result    1 or 0 (output: the check held; trigger: the skill loaded). Leave blank if not run yet.
  evidence  output: the line of output that proves the result. Rows marked 1 without evidence are flagged.

Standard library only. Exit code 1 if a file can't be read or a row is malformed.
"""
import csv
import json
import sys
from collections import defaultdict

COLUMNS = ["kind", "model", "config", "case", "run", "check", "expected", "result", "evidence"]


def load(paths):
    rows, errors = [], []
    for path in paths:
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
                if missing:
                    errors.append(f"{path}: missing columns {missing}")
                    continue
                for n, r in enumerate(reader, start=2):
                    r = {k: (r.get(k) or "").strip() for k in COLUMNS}
                    if not r["result"]:
                        continue  # not run yet
                    if r["result"] not in ("0", "1"):
                        errors.append(f"{path}:{n}: result must be 0 or 1, got {r['result']!r}")
                        continue
                    if r["kind"] not in ("output", "trigger"):
                        errors.append(f"{path}:{n}: kind must be output or trigger, got {r['kind']!r}")
                        continue
                    if r["kind"] == "output" and r["config"] not in ("with", "without"):
                        errors.append(f"{path}:{n}: config must be with or without, got {r['config']!r}")
                        continue
                    if r["kind"] == "trigger" and r["expected"] not in ("fire", "no-fire"):
                        errors.append(f"{path}:{n}: expected must be fire or no-fire, got {r['expected']!r}")
                        continue
                    r["result"] = int(r["result"])
                    r["_where"] = f"{path}:{n}"
                    rows.append(r)
        except (OSError, UnicodeDecodeError) as e:
            errors.append(f"{path}: {e}")
    return rows, errors


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def report(rows):
    out = {"models": {}}
    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"] or "(no model)"].append(r)
    for model, rs in sorted(by_model.items()):
        m = {}
        # --- output checks: pass rate per config, per check ---
        outp = [r for r in rs if r["kind"] == "output"]
        tot = {c: [0, 0] for c in ("without", "with")}
        checks = defaultdict(lambda: {"without": [0, 0], "with": [0, 0]})
        no_evidence = []
        for r in outp:
            tot[r["config"]][0] += r["result"]; tot[r["config"]][1] += 1
            key = f"case {r['case']}: {r['check']}"
            checks[key][r["config"]][0] += r["result"]; checks[key][r["config"]][1] += 1
            if r["result"] == 1 and not r["evidence"]:
                no_evidence.append(r["_where"])
        rate = {c: pct(*tot[c]) for c in tot}
        m["output"] = {"pass_rate_without": rate["without"], "pass_rate_with": rate["with"],
                       "runs_without": tot["without"][1], "runs_with": tot["with"][1],
                       "delta_points": (round(rate["with"] - rate["without"], 1)
                                        if None not in (rate["with"], rate["without"]) else None)}
        always_pass, always_fail, skill_wins, skill_hurts = [], [], [], []
        for key, v in sorted(checks.items()):
            w, wo = v["with"], v["without"]
            if w[1] and wo[1]:
                if w[0] == w[1] and wo[0] == wo[1]: always_pass.append(key)
                elif w[0] == 0 and wo[0] == 0: always_fail.append(key)
                elif w[0] / w[1] > wo[0] / wo[1]: skill_wins.append(key)
                elif w[0] / w[1] < wo[0] / wo[1]: skill_hurts.append(key)
        m["checks"] = {"passes_both_ways": always_pass, "fails_both_ways": always_fail,
                       "skill_helps": skill_wins, "skill_hurts": skill_hurts}
        m["passes_without_evidence"] = no_evidence
        # --- trigger tests: load rate per query, pass at >= 2/3 (fire) or <= 1/3 (no-fire) ---
        trig = defaultdict(lambda: [0, 0, ""])
        for r in rs:
            if r["kind"] != "trigger":
                continue
            t = trig[(r["case"], r["check"])]
            t[0] += r["result"]; t[1] += 1; t[2] = r["expected"]
        tp, failed = 0, []
        for (case, query), (loads, runs, exp) in sorted(trig.items()):
            rate_ = loads / runs
            ok = rate_ >= 2 / 3 - 1e-9 if exp == "fire" else rate_ <= 1 / 3 + 1e-9
            tp += ok
            if not ok:
                failed.append(f"{case} ({exp}, loaded {loads}/{runs}): {query}")
        m["triggers"] = {"queries": len(trig), "passed": tp, "failed": failed}
        out["models"][model] = m
    return out


def verdict(m):
    o, t = m["output"], m["triggers"]
    notes = []
    if o["delta_points"] is not None:
        if o["delta_points"] <= 0:
            notes.append("The skill adds nothing (or hurts) on these cases: fix it, or retire it if the model now passes without it.")
        elif o["pass_rate_with"] is not None and o["pass_rate_with"] < 100:
            notes.append("The skill helps but some checks still fail with it: read those transcripts and fix the instructions.")
        else:
            notes.append("The skill helps and every check passes with it.")
    if m["checks"]["passes_both_ways"]:
        notes.append("Some checks pass with and without the skill: they don't measure the skill. Replace them with harder cases.")
    if m["checks"]["skill_hurts"]:
        notes.append("Some checks do worse with the skill: look for an instruction the agent follows when it shouldn't.")
    if t["queries"] and t["failed"]:
        notes.append("Some trigger queries failed: rewrite the description (what, then 'Use when...'), without pasting the failed queries in.")
    if m["passes_without_evidence"]:
        notes.append("Some passes have no evidence: quote the output line, or mark the check 0.")
    return notes


def main(argv):
    as_json = "--json" in argv
    paths = [a for a in argv if a != "--json"]
    if not paths or "-h" in paths or "--help" in paths:
        print(__doc__)
        return 0 if paths else 1
    rows, errors = load(paths)
    for e in errors:
        print(e, file=sys.stderr)
    if errors:
        return 1
    if not rows:
        print("no results yet: fill the 'result' column (1 or 0) and run again", file=sys.stderr)
        return 1
    rep = report(rows)
    if as_json:
        for m in rep["models"].values():
            m["verdict"] = verdict(m)
        print(json.dumps(rep, indent=2))
        return 0
    for model, m in rep["models"].items():
        o, t = m["output"], m["triggers"]
        print(f"== {model}")
        if o["runs_with"] or o["runs_without"]:
            print(f"output checks  without skill: {o['pass_rate_without']}% ({o['runs_without']} checks)"
                  f"   with skill: {o['pass_rate_with']}% ({o['runs_with']} checks)   delta: {o['delta_points']} points")
        for label, key in (("skill helps", "skill_helps"), ("skill hurts", "skill_hurts"),
                           ("passes both ways (not measuring the skill)", "passes_both_ways"),
                           ("fails both ways", "fails_both_ways")):
            if m["checks"][key]:
                print(f"  {label}:")
                for c in m["checks"][key]:
                    print(f"    - {c}")
        if t["queries"]:
            print(f"trigger tests  {t['passed']}/{t['queries']} queries passed")
            for f_ in t["failed"]:
                print(f"    - FAIL {f_}")
        for where in m["passes_without_evidence"]:
            print(f"  no evidence for a pass: {where}")
        for n in verdict(m):
            print(f"-> {n}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
