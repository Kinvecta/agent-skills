"""Tests for skills/status-report/scripts/totals.py. Run: python -m pytest -q evals"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SCRIPT = HERE.parents[1] / "skills" / "status-report" / "scripts" / "totals.py"


def run(csv_name, month="2026-10"):
    out = subprocess.run([sys.executable, str(SCRIPT), str(HERE / csv_name), "--month", month],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_counts_match_the_tracker():
    r = run("tracker-2026-10.csv")
    assert r["total"] == 7
    assert r["counts"] == {"done": 2, "in progress": 2, "at risk": 1, "blocked": 1, "not started": 1}


def test_open_tasks_due_this_month_and_next():
    r = run("tracker-2026-10.csv")
    assert [t["task"] for t in r["due_this_month_not_done"]] == [
        "Security scan of new skills", "Q4 training rollout", "Migrate wiki to new host"]
    assert {t["task"] for t in r["due_next_month"]} == {"Budget draft for FY27", "Update onboarding guide"}
    assert r["problems"] == []


def test_tricky_rows_are_flagged_not_guessed():
    r = run("tracker-tricky.csv")
    assert r["counts"]["done"] == 1  # "Done " with a trailing space still counts
    assert any("bad due date '10/31/2026'" in p for p in r["problems"])


def test_december_rolls_over_to_january():
    r = run("tracker-2026-10.csv", month="2026-12")
    assert r["month"] == "2026-12"


def test_bad_month_is_rejected():
    out = subprocess.run([sys.executable, str(SCRIPT), str(HERE / "tracker-2026-10.csv"), "--month", "October"],
                         capture_output=True, text=True)
    assert out.returncode != 0
