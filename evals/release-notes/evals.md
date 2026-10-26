# Evaluations for release-notes

Run each case once without the skill (baseline) and once with it, each in a fresh session. Pass = every check holds. Trigger tests are in [`triggers.md`](triggers.md).

**Steps** (full guide: [`evals/README.md`](../README.md)):

1. `python3 -m pytest -q evals tools` passes.
2. Copy [`results-template.csv`](results-template.csv) to `evals/release-notes/results/<date>-<model>.csv`.
3. For each case: run the prompt in a new session **without** the skill, then in a new session **with** it. Save both replies.
4. Grade every check in the sheet: `1` only with the output line pasted in `evidence`, otherwise `0`.
5. Run the trigger queries in [`triggers.md`](triggers.md) 3 times each and record whether the skill loaded.
6. Score it: `python3 tools/eval_report.py evals/release-notes/results/<your-sheet>.csv`
7. Fix one thing, re-run, and repeat on every model you use.

| # | Prompt | Checks |
|---|---|---|
| 1 | "Write the release notes for 1.4.0 from evals/release-notes/git-log-1.4.0.txt" | Header says 1.4.0. Features: CSV export (#142), upload progress bar (#138). Fixes: 503 retry (#140), config path with spaces (#137). Other: docs (#135), search index (#134). No chore or ci commits listed. Contributors: Ana Ruiz, Raj Patel, Sam Okafor. No breaking section. |
| 2 | "What's new in v1.4.0? Draft a changelog entry" (same file) | The skill triggers from the description. Same entries as case 1. No PR number appears that isn't in the log. |
| 3 (tricky) | "Draft the release notes for v2.0.0 from evals/release-notes/git-log-tricky.txt" | Breaking changes come first: tidy.toml (#152) with the migration step "rename tidy.ini to tidy.toml and run `tidy config migrate` once", and the Python 3.9 drop (#146) with a question asking for its migration note. The bulk delete endpoint (#151) is not listed (it was reverted). The squash-body bullets ("add toml loader", "typo in loader") are not separate entries. dependabot and renovate are not credited. The malformed line "feat(api add pagination..." is raised as a question, not guessed. Header says 2.0.0. |

What to look for in the baseline: models without the skill tend to list the reverted endpoint, thank dependabot, miss the breaking change in the commit body, and turn the squash bullets into entries.

The script itself is tested automatically by `test_group_changes.py` (run `python3 -m pytest -q evals tools` from the repo root).
