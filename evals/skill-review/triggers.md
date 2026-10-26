# Trigger tests for skill-review

Same method as [`evals/release-notes/triggers.md`](../release-notes/triggers.md): fresh session, 3 runs per query, should-trigger passes at 2 of 3 loads, should-not at most 1 of 3.

Record each run in the trigger rows of [`results-template.csv`](results-template.csv) (`result` = 1 if the skill loaded) and score with `python3 tools/eval_report.py evals/skill-review/results/<your-sheet>.csv`. Full steps: [`evals/README.md`](../README.md#step-5-trigger-tests).

## Should trigger (10)

1. Review this skill: .claude/skills/deploy-preview/
2. can you lint my SKILL.md before I push it
3. Grade the skills in this folder poor, good or great
4. Why doesn't my pdf-forms skill ever load? Check the SKILL.md
5. Audit the skill I just wrote and tell me what to fix
6. Is this a good agent skill? (pastes a SKILL.md)
7. Improve the description of my changelog skill so it triggers
8. Score skills/status-report against the rubric
9. Check this skill folder for problems before we add it to the team library
10. What's wrong with this SKILL.md, it's 700 lines

## Should not trigger (10 near-misses)

1. Write a new skill that drafts invoices from our billing export
2. Review this pull request
3. Lint my Python code
4. Review my AGENTS.md
5. Is this prompt any good? (a system prompt, not a skill)
6. Scan this skill for malware before I install it
7. Install the release-notes skill into this project
8. Explain what an agent skill is
9. Review my resume and list the skills section problems
10. Grade these student essays against the rubric
