"""Count tracker rows for the monthly status report.

Usage: python3 totals.py tracker.csv --month YYYY-MM
Prints JSON. Expects columns: task, owner, status, due (YYYY-MM-DD).
Status values: done, in progress, at risk, blocked, not started.
"""
import argparse
import csv
import datetime as dt
import json
import sys

STATUSES = ["done", "in progress", "at risk", "blocked", "not started"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--month", required=True, help="report month, YYYY-MM")
    a = ap.parse_args()
    try:
        y, m = map(int, a.month.split("-"))
        start = dt.date(y, m, 1)
    except ValueError:
        sys.exit("--month must look like 2026-10")
    end = dt.date(y + (m == 12), m % 12 + 1, 1)  # first day of next month
    nxt = dt.date(end.year + (end.month == 12), end.month % 12 + 1, 1)

    counts = {s: 0 for s in STATUSES}
    open_due, upcoming, problems = [], [], []
    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
            status = row.get("status", "").lower()
            if status not in counts:
                problems.append(f"line {n}: unknown status '{status}'")
                continue
            counts[status] += 1
            try:
                due = dt.date.fromisoformat(row.get("due", ""))
            except ValueError:
                problems.append(f"line {n}: bad due date '{row.get('due')}'")
                continue
            item = {"task": row.get("task"), "owner": row.get("owner"), "due": due.isoformat()}
            if status != "done" and due < end:
                open_due.append(item)
            elif status != "done" and end <= due < nxt:
                upcoming.append(item)

    print(json.dumps({"month": a.month, "total": sum(counts.values()), "counts": counts,
                      "due_this_month_not_done": open_due, "due_next_month": upcoming, "problems": problems}, indent=2))


if __name__ == "__main__":
    main()
