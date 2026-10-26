# How to run the evals

Every skill in this repo comes with three kinds of tests:

| **test** | **what it answers** | **file** |
|---|---|---|
| Script tests | Does the bundled script do exactly what `SKILL.md` promises? | `evals/<skill>/test_*.py` (pytest, automated) |
| Output evals | Does the agent do the job better **with** the skill than **without** it? | `evals/<skill>/evals.md` |
| Trigger tests | Does the skill load when it should, and stay out of the way when it shouldn't? | `evals/<skill>/triggers.md` |

The script tests run on every push. The output evals and trigger tests need a real agent, so you run them by hand (or with your agent's headless mode) and record the results in a sheet. `tools/eval_report.py` then does the scoring.

The method follows the [agentskills.io guide to evaluating skills](https://agentskills.io/skill-creation/evaluating-skills) and Anthropic's [skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) ("create evaluations before writing extensive documentation"; test with every model you plan to use).

## Step 1: run the script tests

```bash
python3 -m pip install pytest
python3 -m pytest -q evals tools
```

If these fail, stop. An agent can't follow a skill whose script is broken.

## Step 2: set up two clean configurations

You need the same agent and model, twice:

- **without**: the skill is not installed anywhere the agent can see it (check personal folders like `~/.claude/skills/` too).
- **with**: only this skill is copied in, for example `cp -R skills/release-notes /path/to/test-project/.claude/skills/`.

Use a scratch project folder that has the sample files from `evals/<skill>/`. Start a **new session for every run**, so nothing carries over from an earlier run or from writing the skill.

## Step 3: copy the results sheet

```bash
mkdir -p evals/release-notes/results
cp evals/release-notes/results-template.csv evals/release-notes/results/2026-10-25-sonnet.csv
```

Each skill has a `results-template.csv` with one row per check, for both configurations, plus three rows per trigger query. Put the model and agent in the `model` column (for example `claude-sonnet / Claude Code`). Use one sheet per model.

## Step 4: run the output evals

For each case in `evals.md`:

1. **Without** the skill: new session, paste the prompt exactly as written, save the full reply (and the transcript, if your agent shows tool calls).
2. **With** the skill: new session, same prompt, save the reply.
3. **Grade each check**: put `1` in `result` only if you can point to the line of output that proves it, and paste that line into `evidence`. If you can't point to it, it's a `0`. Don't give the benefit of the doubt.

Run baseline first, so you see the failures the skill is supposed to fix. To measure variance, copy the rows and run each case 2–3 times (`run` = 2, 3).

## Step 5: trigger tests

For each query in `triggers.md`, in the **with** configuration:

1. New session. Send the query. Don't mention the skill.
2. Record whether the skill loaded (`1`) or not (`0`). In most agents you can see this in the transcript: the skill's name appears as it's loaded or used.
3. Run each query 3 times (the sheet already has rows for runs 1–3).

A should-trigger query (`fire`) passes if the skill loads at least 2 of 3 times. A near-miss (`no-fire`) passes if it loads at most 1 of 3 times.

## Step 6: score it

```bash
python3 tools/eval_report.py evals/release-notes/results/2026-10-25-sonnet.csv
```

It prints the pass rate without and with the skill and the difference in points, then sorts each check into four groups:

- **skill helps**: passes more often with the skill. This is the value the skill adds.
- **skill hurts**: passes less often with it. Look for an instruction the agent follows when it shouldn't.
- **passes both ways**: the check doesn't measure the skill. Replace it with a harder case.
- **fails both ways**: the skill doesn't fix this yet.

It also lists the trigger queries that failed and any pass recorded without evidence, and ends with a short verdict. Add `--json` for machine-readable output.

## Step 7: decide, change one thing, run again

| **result** | **what to do** |
|---|---|
| With-skill pass rate is higher, every check passes | Keep it. Re-run after every edit, and when you change models. |
| With-skill pass rate is higher, some checks still fail | Read those transcripts, not just the final replies. Add the missing step or gotcha, then re-run. |
| No difference, or worse | The skill adds nothing here. Cut what the model already does well, or retire the skill. |
| Should-trigger queries fail | Rewrite the description: what it does, then "Use when..." with the words people type. Don't paste the failed queries in word for word; that overfits. Hold back a few queries to check the new description on. |
| Near-misses fire | Narrow the description and add a "Not for" line. |

Change one thing at a time, so you know what fixed it.

## Step 8: repeat on every model you use

The same skill can help one model and hurt another: in one study that happened on 36.78% of tasks ([Cheng et al., Oct 2026](https://arxiv.org/abs/2610.08875), preprint). Keep one sheet per model in `evals/<skill>/results/`. When a newer model passes the cases **without** the skill, the skill may be ready to retire.

## Running it headless (optional)

Most agents have a non-interactive mode you can loop over the prompts with, for example Claude Code's print mode (`claude -p "<prompt>"`). Run each prompt from a folder with the skill installed and from one without it, save each reply to a file, then grade them as in step 4. Flags and output formats change, so check your agent's current docs. Grading stays a human job (or a second model with the checks as a rubric), and you still need evidence for every pass.

For Claude Code, this repo has the loop ready made. Each skill's prompts, sample files and checks are in `evals/<skill>/cases.json`.

```bash
# plan first: prints every run and the count, runs nothing
python3 tools/run_claude_evals.py --skill release-notes --models haiku,sonnet --runs 2 --out eval-runs --dry-run
# output evals, without and with the skill (a fresh session and scratch project per run)
python3 tools/run_claude_evals.py --skill release-notes --models haiku,sonnet --runs 2 --out eval-runs
# trigger tests: every skill in skills/ installed together, did release-notes load?
python3 tools/run_claude_evals.py --skill release-notes --triggers --models haiku,sonnet --runs 3 --out eval-runs
# grade the output runs with a second model; a pass whose quote isn't in the reply becomes a 0
python3 tools/grade_runs.py eval-runs
python3 tools/eval_report.py eval-runs/csv/release-notes__sonnet.csv
```

Each run's full transcript, reply and `meta.json` (skills listed and loaded, cost, time, files changed) are kept under `eval-runs/runs/`, and an interrupted run picks up where it stopped. Check the `skills_listed` field: if a personal skill with the same name shows up there, your baseline isn't clean. Read a sample of the graded checks yourself before you trust the numbers; the grader is a model too.

## Files

| **skill** | **output evals** | **trigger tests** | **results sheet** | **script tests** |
|---|---|---|---|---|
| status-report | [evals.md](status-report/evals.md) | [triggers.md](status-report/triggers.md) | [results-template.csv](status-report/results-template.csv) | [test_totals.py](status-report/test_totals.py) |
| release-notes | [evals.md](release-notes/evals.md) | [triggers.md](release-notes/triggers.md) | [results-template.csv](release-notes/results-template.csv) | [test_group_changes.py](release-notes/test_group_changes.py) |
| skill-review | [evals.md](skill-review/evals.md) | [triggers.md](skill-review/triggers.md) | [results-template.csv](skill-review/results-template.csv) | [test_lint_skill.py](skill-review/test_lint_skill.py) |

Writing evals for your own skill: start with 3 cases (one normal, one phrased differently so it tests the trigger, one tricky), write checks you can verify from the output, and about 20 trigger queries, half of them near-misses that share words with the skill but need something else.
