"""Tests for tools/eval_report.py and the results-template.csv sheets."""
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import eval_report  # noqa: E402

COLS = eval_report.COLUMNS


def write(tmp_path, rows, name="r.csv"):
    p = tmp_path / name
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({**{c: "" for c in COLS}, **r})
    return p


def out(config, case, check, result, evidence="line", model="m"):
    return dict(kind="output", model=model, config=config, case=case, run=1, check=check,
                expected="pass", result=result, evidence=evidence)


def trig(case, query, expected, results, model="m"):
    return [dict(kind="trigger", model=model, config="with", case=case, run=i + 1, check=query,
                 expected=expected, result=r) for i, r in enumerate(results)]


def test_with_vs_without_and_check_groups(tmp_path):
    p = write(tmp_path, [
        out("without", 1, "a", 0, ""), out("with", 1, "a", 1),   # skill helps
        out("without", 1, "b", 1), out("with", 1, "b", 1),       # passes both ways
        out("without", 1, "c", 0, ""), out("with", 1, "c", 0, ""),  # fails both ways
        out("without", 1, "d", 1), out("with", 1, "d", 0, ""),   # skill hurts
    ])
    rows, errors = eval_report.load([p])
    assert not errors
    m = eval_report.report(rows)["models"]["m"]
    assert m["output"]["pass_rate_without"] == 50.0
    assert m["output"]["pass_rate_with"] == 50.0
    assert m["output"]["delta_points"] == 0.0
    assert m["checks"]["skill_helps"] == ["case 1: a"]
    assert m["checks"]["passes_both_ways"] == ["case 1: b"]
    assert m["checks"]["fails_both_ways"] == ["case 1: c"]
    assert m["checks"]["skill_hurts"] == ["case 1: d"]
    assert any("adds nothing" in n for n in eval_report.verdict(m))


def test_trigger_thresholds(tmp_path):
    p = write(tmp_path, trig("S1", "should fire", "fire", [1, 1, 0])      # 2/3 pass
              + trig("S2", "should fire too", "fire", [1, 0, 0])          # 1/3 fail
              + trig("N1", "near miss", "no-fire", [1, 0, 0])             # 1/3 pass
              + trig("N2", "near miss 2", "no-fire", [1, 1, 0]))          # 2/3 fail
    rows, _ = eval_report.load([p])
    t = eval_report.report(rows)["models"]["m"]["triggers"]
    assert t["queries"] == 4 and t["passed"] == 2
    assert any(f.startswith("S2") for f in t["failed"]) and any(f.startswith("N2") for f in t["failed"])


def test_pass_without_evidence_is_flagged(tmp_path):
    p = write(tmp_path, [out("with", 1, "a", 1, evidence=""), out("without", 1, "a", 0, "")])
    rows, _ = eval_report.load([p])
    m = eval_report.report(rows)["models"]["m"]
    assert len(m["passes_without_evidence"]) == 1


def test_models_are_scored_separately(tmp_path):
    p = write(tmp_path, [out("with", 1, "a", 1, model="A"), out("without", 1, "a", 0, "", model="A"),
                         out("with", 1, "a", 0, "", model="B"), out("without", 1, "a", 1, model="B")])
    rows, _ = eval_report.load([p])
    rep = eval_report.report(rows)["models"]
    assert rep["A"]["output"]["delta_points"] == 100.0
    assert rep["B"]["output"]["delta_points"] == -100.0


def test_blank_results_are_skipped_and_bad_values_rejected(tmp_path):
    p = write(tmp_path, [out("with", 1, "a", ""), out("with", 1, "b", "yes")])
    rows, errors = eval_report.load([p])
    assert rows == [] and len(errors) == 1 and "0 or 1" in errors[0]


def test_cli_exit_codes(tmp_path):
    script = str(ROOT / "tools" / "eval_report.py")
    empty = write(tmp_path, [out("with", 1, "a", "")])
    r = subprocess.run([sys.executable, script, str(empty)], capture_output=True, text=True)
    assert r.returncode == 1 and "no results yet" in r.stderr
    good = write(tmp_path, [out("with", 1, "a", 1), out("without", 1, "a", 0, "")], "g.csv")
    r = subprocess.run([sys.executable, script, str(good), "--json"], capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["models"]["m"]["output"]["delta_points"] == 100.0


def test_every_results_template_is_valid():
    sheets = sorted(ROOT.glob("evals/*/results-template.csv"))
    assert sheets, "each skill needs evals/<skill>/results-template.csv"
    skills = {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}
    assert {s.parent.name for s in sheets} == skills
    for s in sheets:
        with open(s, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows and list(rows[0].keys()) == COLS, s
        configs = {r["config"] for r in rows if r["kind"] == "output"}
        assert configs == {"with", "without"}, s
        trig_rows = [r for r in rows if r["kind"] == "trigger"]
        assert {r["expected"] for r in trig_rows} == {"fire", "no-fire"}, s
        assert all(r["result"] == "" for r in rows), f"{s}: the template must ship with blank results"
