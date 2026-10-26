"""Tests for tools/run_claude_evals.py and tools/grade_runs.py: parsing and scoring only, no network."""
import argparse
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import eval_report  # noqa: E402
import grade_runs  # noqa: E402
import run_claude_evals as rce  # noqa: E402

SKILLS = ["status-report", "release-notes", "skill-review"]


# ---------------------------------------------------------------- triggers.md and cases.json

@pytest.mark.parametrize("skill", SKILLS)
def test_triggers_parse_matches_template(skill):
    qs = rce.parse_triggers((ROOT / "evals" / skill / "triggers.md").read_text())
    assert [q[0] for q in qs] == [f"S{i}" for i in range(1, 11)] + [f"N{i}" for i in range(1, 11)]
    assert {q[2] for q in qs[:10]} == {"fire"} and {q[2] for q in qs[10:]} == {"no-fire"}
    with open(ROOT / "evals" / skill / "results-template.csv", newline="") as f:
        tmpl = {(r["case"], r["check"], r["expected"]) for r in csv.DictReader(f) if r["kind"] == "trigger"}
    assert set(qs) == tmpl


def test_parse_triggers_ignores_other_sections():
    text = "# T\n\n1. not a query\n## Should trigger (2)\n\n1. a\n2. b\n## Notes\n1. no\n## Should not trigger\n1. c\n"
    assert rce.parse_triggers(text) == [("S1", "a", "fire"), ("S2", "b", "fire"), ("N1", "c", "no-fire")]


def test_trigger_prompt_drops_reader_annotation():
    assert rce.trigger_prompt("Is this a good agent skill? (pastes a SKILL.md)") == "Is this a good agent skill?"
    assert rce.trigger_prompt("here's `git log v4.1.0..v4.2.0`, write it up") == "here's `git log v4.1.0..v4.2.0`, write it up"
    assert rce.trigger_prompt("Fix (this) now") == "Fix (this) now"


@pytest.mark.parametrize("skill", SKILLS)
def test_cases_json_checks_match_template(skill):
    cases = json.loads((ROOT / "evals" / skill / "cases.json").read_text())
    tmpl = rce.checks_from_template(ROOT / "evals" / skill / "results-template.csv")
    assert {str(c["id"]): c["checks"] for c in cases} == tmpl
    for c in cases:
        for f in c["files"]:
            src = f if isinstance(f, str) else f["src"]
            assert (ROOT / src).exists(), src
            if isinstance(f, str):  # copied to the project root by basename: the prompt must say so
                assert "/" not in c["prompt"] or Path(src).name in c["prompt"]


# ---------------------------------------------------------------- stream-json

def _ev(**kw):
    return json.dumps(kw)


STREAM = [
    _ev(type="system", subtype="init", model="claude-haiku-x", skills=["release-notes", "debug"], tools=["Bash"],
        claude_code_version="9.9"),
    _ev(type="stream_event", event={}),
    _ev(type="assistant", message={"content": [{"type": "text", "text": "Let me look."},
                                               {"type": "tool_use", "id": "t1", "name": "Skill",
                                                "input": {"skill": "release-notes"}}]}),
    _ev(type="user", message={"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "Launching"}]}),
    _ev(type="assistant", message={"content": [{"type": "tool_use", "id": "t2", "name": "Bash",
                                                "input": {"command": "python3 x.py log.txt"}}]}),
    _ev(type="user", message={"content": [{"type": "tool_result", "tool_use_id": "t2",
                                           "content": [{"type": "text", "text": '{"version": "1.4.0"}'}]}]}),
    "not json",
    _ev(type="result", subtype="success", result="## 1.4.0", total_cost_usd=0.01, duration_ms=1200,
        num_turns=3, is_error=False),
]


def test_parse_stream():
    s = rce.parse_stream(STREAM)
    assert s["model"] == "claude-haiku-x" and s["skills"] == ["release-notes", "debug"]
    assert s["claude_code_version"] == "9.9"
    assert [c["name"] for c in s["tool_calls"]] == ["Skill", "Bash"]
    assert s["tool_calls"][1]["result"] == '{"version": "1.4.0"}'
    assert s["reply"] == "## 1.4.0" and s["cost_usd"] == 0.01 and s["num_turns"] == 3
    assert s["result_seen"]


def test_parse_stream_without_result_falls_back_to_last_text():
    s = rce.parse_stream(STREAM[:3])
    assert not s["result_seen"] and s["reply"] == "Let me look."


def test_skill_loads_counts_skill_tool_and_reading_skill_md():
    calls = [
        {"name": "Skill", "input": {"skill": "release-notes", "args": "1.4.0"}},
        {"name": "Read", "input": {"file_path": "/p/.claude/skills/status-report/SKILL.md"}},
        {"name": "Bash", "input": {"command": "cat .claude/skills/skill-review/SKILL.md"}},
        {"name": "Bash", "input": {"command": "ls .claude/skills/skill-review/SKILL.md"}},   # listing is not loading
        {"name": "Read", "input": {"file_path": "/p/skills/release-notes/SKILL.md"}},      # not installed copy
    ]
    loads = rce.skill_loads(calls)
    assert [(l["skill"], l["via"]) for l in loads] == [
        ("release-notes", "Skill"), ("status-report", "Read"), ("skill-review", "Bash")]
    assert loads[0]["evidence"].startswith("TOOL Skill ")
    assert rce.loaded(loads, "release-notes") and not rce.loaded(loads, "other")
    assert rce.loaded([{"skill": "plugin:release-notes"}], "release-notes")


# ---------------------------------------------------------------- CSV rows feed eval_report

def _meta(**kw):
    m = {"kind": "output", "label": "release-notes", "skill": "release-notes", "model": "haiku",
         "model_id": "claude-haiku-x", "claude_code_version": "9.9", "variant": None, "config": "with",
         "case": "1", "run": 1, "checks": ["a", "b"], "skill_loads": []}
    m.update(kw)
    return m


def test_rows_and_csv_score_with_eval_report(tmp_path):
    runs = tmp_path / "runs"
    metas = [
        (_meta(config="without"), {"checks": [{"check": "a", "result": 0, "evidence": "x"},
                                              {"check": "b", "result": 1, "evidence": "y"}]}),
        (_meta(), {"checks": [{"check": "a", "result": 1, "evidence": "x"},
                              {"check": "b", "result": 1, "evidence": "y"}]}),
        (_meta(kind="trigger", case="S1", query="write notes", expected="fire",
               skill_loads=[{"skill": "release-notes", "via": "Skill", "evidence": "TOOL Skill {}"}]), None),
        (_meta(kind="trigger", case="N1", query="write a tweet", expected="no-fire", run=1,
               skill_loads=[{"skill": "status-report", "via": "Skill", "evidence": "TOOL Skill {}"}]), None),
    ]
    for i, (m, g) in enumerate(metas):
        d = runs / str(i)
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps(m))
        if g:
            (d / "grade.json").write_text(json.dumps(g))
    [p] = rce.write_csvs(tmp_path)
    rows, errors = eval_report.load([p])
    assert not errors
    m = eval_report.report(rows)["models"]["claude-haiku-x / Claude Code 9.9"]
    assert m["output"]["pass_rate_without"] == 50.0 and m["output"]["pass_rate_with"] == 100.0
    assert m["checks"]["skill_helps"] == ["case 1: a"]
    assert m["triggers"] == {"queries": 2, "passed": 2, "failed": []}
    trig = [r for r in csv.DictReader(open(p)) if r["kind"] == "trigger"]
    assert any("loaded instead: status-report" in r["evidence"] for r in trig)


def test_ungraded_and_errored_runs_leave_result_blank():
    [r] = rce.rows_for_meta(_meta(kind="trigger", case="S1", query="q", expected="fire", error="timeout"))
    assert r["result"] == "" and "timeout" in r["evidence"]
    rows = rce.rows_for_meta(_meta())
    assert [r["result"] for r in rows] == ["", ""]


def test_variant_goes_in_model_column():
    assert rce.model_label(_meta(variant="release-notes:poor")) == "claude-haiku-x / Claude Code 9.9 / release-notes:poor"


# ---------------------------------------------------------------- plan, install, sandbox

def _args(**kw):
    a = dict(skill="release-notes", skill_dir=None, label=None, variant=None, models="haiku,opus",
             configs="without,with", cases=None, runs=2, triggers=False, queries=None, only_target=False)
    a.update(kw)
    return argparse.Namespace(**a)


def test_plan_counts():
    assert len(rce.build_plan(_args())) == 2 * 3 * 2 * 2
    assert len(rce.build_plan(_args(cases="1,3", configs="with", models="haiku"))) == 4
    assert len(rce.build_plan(_args(triggers=True, runs=3))) == 2 * 20 * 3
    ids = [s["id"] for s in rce.build_plan(_args())]
    assert len(set(ids)) == len(ids)


def test_install_skill_dir_puts_scripts_where_repo_paths_point(tmp_path):
    rce.install_skills(_args(skill_dir="examples/poor-good-great/release-notes/great"), tmp_path)
    assert (tmp_path / ".claude/skills/release-notes/SKILL.md").read_text().startswith("---\nname: release-notes")
    assert (tmp_path / ".claude/skills/release-notes/scripts/group_changes.py").exists()
    assert (tmp_path / "skills/release-notes/scripts/group_changes.py").exists()
    assert (tmp_path / "skills/release-notes/templates/notes.md").exists()
    assert not (tmp_path / "skills/release-notes/SKILL.md").exists()


def test_install_poor_has_no_repo_path_copy(tmp_path):
    rce.install_skills(_args(skill_dir="examples/poor-good-great/release-notes/poor"), tmp_path)
    assert (tmp_path / ".claude/skills/release-notes/scripts/group_changes.py").exists()
    assert not (tmp_path / "skills").exists()


def test_install_trigger_library_installs_every_skill(tmp_path):
    names = rce.install_skills(_args(triggers=True), tmp_path)
    assert set(SKILLS) <= set(names)
    assert not list(tmp_path.rglob("__pycache__"))


def test_place_files_basename_and_dest(tmp_path):
    rce.place_files(["evals/release-notes/git-log-1.4.0.txt",
                     {"src": "evals/skill-review/fixtures/csv-cleanup", "dest": "x/csv-cleanup"}], tmp_path)
    assert (tmp_path / "git-log-1.4.0.txt").exists() and (tmp_path / "x/csv-cleanup/SKILL.md").exists()


def test_snapshot_diff(tmp_path):
    (tmp_path / "a").write_text("1")
    before = rce.snapshot(tmp_path)
    (tmp_path / "a").write_text("2")
    (tmp_path / "b").write_text("3")
    assert rce.diff_snapshots(before, rce.snapshot(tmp_path)) == {"added": ["b"], "deleted": [], "modified": ["a"]}


def test_sandbox_script_hides_then_restores(tmp_path):
    s = rce.sandbox_script(tmp_path / "w", ["claude", "-p", "hi there"], ["/home", "/tmp"], ["/home/u/.auth"])
    lines = s.splitlines()
    first_hide = next(i for i, l in enumerate(lines) if "mount -t tmpfs none /home" in l)
    assert any("keep0" in l and "mount --bind /home/u/.auth" in l for l in lines[:first_hide])
    assert lines[-1].startswith("exec claude -p 'hi there'")
    assert "cd /home/dev/project" in lines


def test_child_env_unsets_sync_vars(monkeypatch):
    for var in ("CLAUDE_CODE_SYNC_SKILLS", "CLAUDE_PROJECT_UUID", "CLAUDE_CODE_USER_EMAIL"):
        monkeypatch.setenv(var, "1")
    env = rce.child_env("/tmp/h")
    assert env["HOME"] == "/tmp/h"
    assert not {"CLAUDE_CODE_SYNC_SKILLS", "CLAUDE_PROJECT_UUID", "CLAUDE_CODE_USER_EMAIL"} & set(env)


# ---------------------------------------------------------------- grader helpers

def test_evidence_found_is_strict_but_ignores_markup():
    hay = "## 1.4.0 (2026-10-25)\n\n- **CSV export:** run `--format csv` (#142)\n### Fixes"
    assert grade_runs.evidence_found("CSV export: run --format csv (#142)", hay)
    assert grade_runs.evidence_found('"## 1.4.0 (2026-10-25)"', hay)
    assert grade_runs.evidence_found("## 1.4.0 ... ### Fixes", hay)
    assert grade_runs.evidence_found("### Fixes ... ## 1.4.0", hay)       # fragments in any order
    assert not grade_runs.evidence_found("## 1.4.0 ... ### Features", hay)  # every fragment must be there
    assert not grade_runs.evidence_found("The reply has a 1.4.0 header", hay)
    assert not grade_runs.evidence_found("", hay)


def test_parse_grader_json():
    text = '```json\n{"checks": [{"n": 1, "result": 1, "evidence": "a"}, {"n": 2, "result": 0, "evidence": ""}]}\n```'
    assert grade_runs.parse_grader_json(text, 2) == {1: {"result": 1, "evidence": "a"}, 2: {"result": 0, "evidence": ""}}
    assert grade_runs.parse_grader_json('{"checks": [{"n": 1, "result": 1, "evidence": "a"}]}\n{"x": 1}', 1)
    with pytest.raises(ValueError):
        grade_runs.parse_grader_json('{"checks": [{"n": 1, "result": 1}]}', 2)
    with pytest.raises(ValueError):
        grade_runs.parse_grader_json("no json here", 1)
    with pytest.raises(ValueError):
        grade_runs.parse_grader_json('{"checks": [{"n": 1, "result": 2}]}', 1)


def test_load_checks_are_decided_from_transcript():
    m = _meta(skill_loads=[{"skill": "release-notes", "via": "Skill", "evidence": "TOOL Skill {\"skill\": \"release-notes\"}"}])
    g = grade_runs.deterministic("The skill loaded from the description", m)
    assert g["result"] == 1 and g["evidence"].startswith("TOOL Skill")
    g = grade_runs.deterministic("The skill loaded from the description (prompt never says 'status report')",
                                 _meta(config="without"))
    assert g["result"] == 0
    assert grade_runs.deterministic("Header says 1.4.0", m) is None


def test_transcript_text_lists_calls_and_file_changes():
    m = _meta(tool_calls=[{"line": "TOOL Bash {}", "result": "x" * 5000}],
              files_changed={"added": ["NOTES.md"], "modified": [], "deleted": []})
    t = grade_runs.transcript_text(m, max_result=100)
    assert "TOOL Bash {}" in t and "...[cut]" in t and "FILES CHANGED: added NOTES.md" in t
    assert "FILES CHANGED: none" in grade_runs.transcript_text(_meta(tool_calls=[], files_changed={}))


def test_apply_grades_downgrades_unquoted_pass():
    m = _meta(checks=["Header says 1.4.0", "No breaking section", "The skill loaded from the description"])
    by_n = {1: {"result": 1, "evidence": "## 1.4.0"}, 2: {"result": 1, "evidence": "there is no breaking section"},
            3: {"result": 1, "evidence": "it loaded"}}
    out = grade_runs.apply_grades(m, by_n, "## 1.4.0\n### Features")
    assert [c["result"] for c in out] == [1, 0, 0]
    assert out[1]["downgraded"] and out[1]["evidence"].startswith("[downgraded")
    assert out[2]["by"] == "transcript" and out[2]["grader_result"] == 1
