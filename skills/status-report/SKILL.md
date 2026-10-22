---
name: status-report
description: Drafts the monthly project status report from the project tracker CSV. Use when the user asks for a status report, a monthly update, or a project roll-up for leadership.
---

# Status report

Turns the project tracker export into the team's one-page monthly status report.

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
   If any check fails, fix the draft and check again.

## Output

Return the filled report as Markdown. Do not send or post it; a person reviews it first.
