# Experiment, 25 October 2026: we tested our own skills

Data behind the video *How to test an agent skill*. Everything here can be re-run with `tools/run_claude_evals.py`, graded with `tools/grade_runs.py` and scored with `tools/eval_report.py` (steps in [`../README.md`](../README.md)).

| file | what |
|---|---|
| `../<skill>/results/2026-10-25-<model>.csv` | output and trigger results per skill and model (part A and C) |
| `../../examples/poor-good-great/results/` | poor / good / great results (part B) |
| `status-report-before-*.csv`, `status-report-fixed-*.csv` | the tricky case re-run before and after adding a gotcha to status-report (2 of 9 → 9 of 9 flagged the bad date) |
| `hand-check.csv` | 20 grades checked by hand: 18 agree (one borderline, see notes) |
| `runs.tar.gz` | every run: reply, transcript (tool calls and truncated tool output; emails and token-like strings removed), meta (cost, time, skill loads) and grades |

Summary below. Small sample (2 runs per case), a model grader, and tests written by the skills' author: treat it as a worked example, not a benchmark.


Setup: models claude-haiku-5-5, claude-sonnet-5-5, claude-opus-5-5; harness Claude Code 2.1.310 headless (`claude -p --output-format stream-json`); grader claude-sonnet-5-5 with verbatim-evidence check. Fresh scratch project + empty HOME per run, `--setting-sources project`, sync/project/email env vars unset, mount-namespace sandbox. Skills visible: installed repo skill(s) + 24 Claude Code built-ins. Tools: Bash, Read, Write, Edit, Skill, todo; Task/publish/browse disallowed. CLAUDE_EFFORT=medium inherited.

Runs: A 108 (3 skills × 3 cases × without/with × 3 models × 2) · B output 36 (poor/good/great, cases 1+3) · B triggers 360 (20 q × 3 levels × 3 models × 2) · C triggers 540 (20 q × 3 skills × 3 models × 3). 1,044 agent runs, 0 errors, + 432 grader calls. Cost v2 $39.67 ($78.12 incl. discarded first run that leaked host context).

## A. Output checks, without → with
| skill | haiku | sonnet | opus |
|---|---|---|---|
| status-report | 59% → 91% | 64% → 86% | 64% → 100% |
| release-notes | 67% → 100% | 72% → 100% | 72% → 100% |
| skill-review | 10% → 85% | 20% → 90% | 30% → 95% |
| all 78 checks | 50% → 94% | 56% → 94% | 59% → 99% |
Runs passing every check: 2/54 without, 43/54 with.

## B. Poor / good / great (release-notes cases 1+3, 30 checks/model)
| model | none | poor | good | great | installable |
|---|---|---|---|---|---|
| haiku | 67% | 67% | 93% | 100% | 100% |
| sonnet | 73% | 77% | 87% | 100% | 100% |
| opus | 77% | 80% | 93% | 100% | 100% |
Poor loaded every time but ran the script in 5/12. Good ran the script 12/12 but missed "raise as a question" checks. Great 12/12 perfect.
B triggers (should-fire / near-miss load rate, queries passed /20): haiku poor 50/10 (12), good 70/10 (14), great 55/5 (13); sonnet 50/0 (15), 85/10 (17), 90/10 (17); opus 75/5 (16), 90/35 (15), 90/40 (14).

## C. Triggers, all 3 skills installed
status-report 20/20 all models; release-notes 15/19/18; skill-review 17/17/17. release-notes misses = queries pointing at absent content ("git log is pasted below"). Near-miss "loads" were all SKILL.md reads while exploring the empty project; the skill under test was never called on any of the 450 near-miss runs (other skills were, 30 times). N9 "monthly status report" routed to status-report every time.

## Cost/time per output run (mean, without vs with)
haiku $0.0027/16.2 s vs $0.0035/18.8 s · sonnet $0.0355/13.7 s vs $0.0397/14.0 s · opus $0.0952/26.8 s vs $0.0932/22.9 s.

## Checks passing both ways on all 3 models: 13 of 39 (10 in release-notes).

## Surprises
1. status-report bad date flagged without guessing 0/6 without, 3/6 with ("I read it as 2026-10-31"). SKILL.md never mentioned `problems`; no Gotchas. → fix + re-run below.
2. skill-review case 3, Haiku with skill wrote to the fixture after "make it great".
3. Baselines: 0/6 listed contributors; 0/6 raised malformed line or Python 3.9 question; Haiku listed CI/version bumps as changes.
4. skill-review score checks can only pass with the linter (built into checks).
5. status-report template header "2026-10" tripped the "every date YYYY-MM-DD" check (bad check).

## Grading quality
Repeat grading agreement 95.5% (682/714); human spot check 18/20; 15/738 passes downgraded for non-verbatim quotes.

## Caveats
n small (2 runs/case); grader is a model of the same family; built-ins present; single-turn headless; "loaded" includes SKILL.md reads; some checks only passable with the skill; cases written by the skill author.
