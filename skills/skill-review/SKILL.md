---
name: skill-review
description: Reviews an Agent Skill (a folder with a SKILL.md) for the problems that make skills fail to fire, overload the context or go unchecked, and grades it poor, good or great. Use when the user asks to review, lint, grade, audit or improve a skill or a SKILL.md file.
---

# Skill review

Grades one skill folder against the poor / good / great rubric and names the few fixes that matter most.

Not for: writing a new skill from scratch, security sign-off (the script spots a few risky patterns; it is not a scanner), or reviewing ordinary code or prompts that aren't skills.

## Gotchas

- **The score is a floor, not a verdict.** The script checks that a Gotchas section exists, not that its items are real. A skill can score 10 with generic advice ("handle errors appropriately") in every section. Your judgment pass decides that.
- **"check" is not "fail".** A body over 150 lines, three all-caps words or a list of options can be right for that skill. Look at the line before you report it.
- **Evals live outside the folder in many repos** (`evals/<name>/`). If the script finds none, ask before you say the skill is untested.
- **Don't edit the skill.** Report only, unless the user asks you to apply the fixes. A skill runs with the agent's permissions, so a person reviews every change.

## Steps

1. Run the linter on the folder the user names (the folder that holds `SKILL.md`):
   `python3 scripts/lint_skill.py <skill_dir> --json`
   It prints a score out of 10, a level, and findings tagged poor, good or great with pass, check or fail.
2. Read `SKILL.md` and every file it mentions. Then judge what the script can't:
   - **Gotchas:** is each one a concrete trap the agent would hit (a field name, a command, a wrong default), or generic advice it already follows?
   - **Scope:** is it one job? Would a request for a neighbouring job wrongly trigger it?
   - **The cut test:** for each instruction, would the agent get it wrong without it? If not, it's a cut.
   - **Fragile steps:** are counts, dates, deletions or other exact work done by a script, not prose?
   - **Must-hold rules:** is any rule one that must hold every time? Suggest a hook.
3. Pick the top 3 fixes: the ones most likely to change whether the skill fires or gets the job right. Fixes for "fail" findings usually come first.

## Check before you answer

- [ ] the score and level are the script's, unchanged
- [ ] each of the 3 fixes points at a line or section, and says what to write instead
- [ ] you judged the gotchas and scope yourself, not only the script's findings
- [ ] no file in the skill was changed, unless the user asked you to apply the fixes

## Output

Use `templates/review.md`. Keep it under one screen.
