# Trigger tests for status-report

Same method as the other skills (full steps in [`evals/README.md`](../README.md#step-5-trigger-tests)): fresh session, 3 runs per query, should-trigger passes at 2 of 3 loads, should-not at most 1 of 3.

Record each run in the trigger rows of [`results-template.csv`](results-template.csv) (`result` = 1 if the skill loaded) and score with `python3 tools/eval_report.py evals/status-report/results/<your-sheet>.csv`. Full steps: [`evals/README.md`](../README.md#step-5-trigger-tests).

## Should trigger (10)

1. Draft the October status report from tracker-2026-10.csv
2. Give leadership a monthly update for 2026-10 from the tracker export
3. I need the project roll-up for this month, the CSV is attached
4. what's at risk and what's blocked this month? write it up for my director
5. Turn this tracker export into the one-page monthly report
6. Monthly status update please, tracker.csv is in this folder
7. Summarize the project tracker for the steering committee, month of September
8. Which tasks are due this month and not done? Put it in our report format
9. Write the status report for 2026-11
10. Can you do the usual monthly project update from the task list?

## Should not trigger (10 near-misses)

1. Draft the release notes for v1.4.0
2. Write my weekly 1:1 notes for my manager
3. Clean up this CSV: trim spaces and fix the date column
4. Make a chart of tasks by owner from tracker.csv
5. What's the status of PR #142?
6. Write a project kickoff plan for the Q1 migration
7. Summarize this meeting transcript
8. Draft an incident report for yesterday's outage
9. Convert tracker.csv to Excel
10. Write a performance review for Sam
