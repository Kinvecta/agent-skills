---
name: status-report
description: Drafts the monthly project status report from the project tracker CSV. Use when the user asks for a status report, a monthly update, or a project roll-up for leadership.
---

# Status report

Turns the project tracker export into the team's one-page monthly status report.

## Gotchas

- **A row the script can't read is a question, not a guess.** The JSON has a `problems` list (a bad date such as `10/31/2026`, an unknown status). Never reinterpret those rows yourself, even when the meaning looks obvious: list each one under the report as a question for the user, and leave it out of the totals the script didn't count.
- **The report month is `YYYY-MM`** (the header says `2026-10`); dates of tasks are always full `YYYY-MM-DD`.

## Steps

1. Find the tracker CSV the user names (it has the columns `task, owner, status, due`). If none is given, ask for it.
2. Run the totals script. Do not count rows yourself:
   `python3 scripts/totals.py <tracker.csv> --month YYYY-MM`
   It prints JSON with the counts, the tasks due this month that are not done, and the tasks due next month.
3. Fill `templates/report.md`. Every number must come from the script's JSON.
4. Follow `references/style.md` for tone and length (read it only when you write the summary).
5. Check before you answer:
   - the totals in the report match the JSON exactly
   - every date is in `YYYY-MM-DD` form and falls in the right month
   - each open task names its owner
   - every item in the JSON's `problems` list appears as a question, and none was silently fixed
   If any check fails, fix the draft and check again.

## Output

Return the filled report as Markdown. Do not send or post it; a person reviews it first.
