# Evaluations for status-report

Run each case once without the skill (baseline) and once with it. Pass = every check holds.

| # | Prompt | Checks |
|---|---|---|
| 1 | "Draft the October status report from evals/status-report/tracker-2026-10.csv" | Totals 2 done / 2 in progress / 1 at risk / 1 blocked / 1 not started / 7 total. Due this month, not done: "Security scan of new skills" (Raj), "Q4 training rollout" (Lee), "Migrate wiki to new host" (Sam). |
| 2 | "Give leadership a monthly update for 2026-10" (same CSV) | The skill triggers from the description. Same totals. Due next month lists "Budget draft for FY27" and "Update onboarding guide". |
| 3 (tricky) | "Draft the October status report from evals/status-report/tracker-tricky.csv" (one status is "Done " with a trailing space, one due date is "10/31/2026") | "Done " still counts as done (the script trims spaces). The script lists the bad date under problems, and the report flags that row instead of guessing. |

The script itself is tested automatically by `test_totals.py` (run `python -m pytest -q evals`).
