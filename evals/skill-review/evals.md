# Evaluations for skill-review

Run each case once without the skill (baseline) and once with it, each in a fresh session. Pass = every check holds. Trigger tests are in [`triggers.md`](triggers.md).

**Steps** (full guide: [`evals/README.md`](../README.md)):

1. `python3 -m pytest -q evals tools` passes.
2. Copy [`results-template.csv`](results-template.csv) to `evals/skill-review/results/<date>-<model>.csv`.
3. For each case: run the prompt in a new session **without** the skill, then in a new session **with** it. Save both replies.
4. Grade every check in the sheet: `1` only with the output line pasted in `evidence`, otherwise `0`.
5. Run the trigger queries in [`triggers.md`](triggers.md) 3 times each and record whether the skill loaded.
6. Score it: `python3 tools/eval_report.py evals/skill-review/results/<your-sheet>.csv`
7. Fix one thing, re-run, and repeat on every model you use.

| # | Prompt | Checks |
|---|---|---|
| 1 | "Review the skill in examples/poor-good-great/release-notes/poor" | Reports the script's score (2.0/10, poor) unchanged. Top fix 1 is the description: no "Use when" clause and too short to route. Names the missing check step and the missing gotchas. Changes no file. |
| 2 | "Grade skills/status-report against the poor / good / great rubric and tell me the top 3 fixes" | Reports 7.5/10 (good). Fixes include a Gotchas section and a "Not for" line, each with suggested text specific to tracker CSVs (for example, a status with a trailing space, or a date not in `YYYY-MM-DD`), not generic advice. Doesn't say the skill is untested (its evals are in `evals/status-report/`). |
| 3 (tricky) | "Lint evals/skill-review/fixtures/csv-cleanup and make it great" (its Gotchas section exists but holds only "handle errors appropriately" and "follow best practices") | The script passes the gotchas check, but the review says the gotchas are generic and asks for real failures. Because the user said "make it great", it proposes the edits and asks before writing, or applies them only if the request clearly asked to edit. |

What to look for in the baseline: without the skill, models tend to praise the structure, skip the trigger (description) entirely, and not notice that a Gotchas heading full of generic advice adds nothing.

The script itself is tested automatically by `test_lint_skill.py` (run `python3 -m pytest -q evals tools` from the repo root).
