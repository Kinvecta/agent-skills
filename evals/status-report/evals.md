# Evaluations for status-report

Run each case once without the skill (baseline) and once with it. Pass = every check holds.

**Steps** (full guide: [`evals/README.md`](../README.md)):

1. `python3 -m pytest -q evals tools` passes.
2. Copy [`results-template.csv`](results-template.csv) to `evals/status-report/results/<date>-<model>.csv`.
3. For each case: run the prompt in a new session **without** the skill, then in a new session **with** it. Save both replies.
4. Grade every check in the sheet: `1` only with the output line pasted in `evidence`, otherwise `0`.
5. Run the trigger queries in [`triggers.md`](triggers.md) 3 times each and record whether the skill loaded.
6. Score it: `python3 tools/eval_report.py evals/status-report/results/<your-sheet>.csv`
7. Fix one thing, re-run, and repeat on every model you use.

| # | Prompt | Checks |
|---|---|---|
| 1 | "Draft the October status report from evals/status-report/tracker-2026-10.csv" | Totals 2 done / 2 in progress / 1 at risk / 1 blocked / 1 not started / 7 total. Due this month, not done: "Security scan of new skills" (Raj), "Q4 training rollout" (Lee), "Migrate wiki to new host" (Sam). |
| 2 | "Give leadership a monthly update for 2026-10" (same CSV) | The skill triggers from the description. Same totals. Due next month lists "Budget draft for FY27" and "Update onboarding guide". |
| 3 (tricky) | "Draft the October status report from evals/status-report/tracker-tricky.csv" (one status is "Done " with a trailing space, one due date is "10/31/2026") | "Done " still counts as done (the script trims spaces). The script lists the bad date under problems, and the report flags that row instead of guessing. |

The script itself is tested automatically by `test_totals.py` (run `python3 -m pytest -q evals tools` from the repo root).
