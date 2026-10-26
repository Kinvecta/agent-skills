# Skill quality: poor, good, great

A rubric for Agent Skills, drawn from vendor guidance and the 2026 studies of public skills. It goes with the video *Poor, good, great: what makes an agent skill work*, the worked example in [`examples/poor-good-great/`](../examples/poor-good-great/), and the [`skill-review`](../skills/skill-review/) skill, whose linter checks the mechanical rows.

Most skills fail before they run: they never fire, they say too much, or nobody checked them. Good skills fix the trigger, the length and the fragile steps. Great skills add what only you know, say where they stop, and show they still help.

Preprints are not peer-reviewed. "Vendor" means a company evaluating its own product or publishing its own guidance. SkillsBench numbers are from v4 (June 2026); earlier versions report different numbers.

## Poor: why skills fail

| marker | evidence | source |
|---|---|---|
| **Never fires.** A vague description with no "use when" | 52.3% of 138,133 public skills have no trigger guidance (preprint). In one vendor eval, the skill was never invoked in 56% of eval cases and scored the same as no skill (53%) | [Zhang et al., Aug 2026](https://arxiv.org/abs/2608.08453); [Vercel, Jan 2026](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) (vendor) |
| **Lost in a crowd.** Too many skills installed | Recall of the right skill fell from 73.6% to 27.4% as unrelated skills grew from 0 to 1,000; at 1,000, the agent loaded no skill at all in 51.6% of runs. Pooled over three open-weight models (preprint) | [Liu et al., Oct 2026](https://arxiv.org/abs/2610.18522) |
| **Says too much.** A manual, not a skill | Tasks grouped by the size of their skills: compact +19.0 points, standard +21.5, detailed +14.5, comprehensive +0.7 (only 5 tasks). A correlation across different tasks, not a length experiment (preprint). Skills over 500 lines average 4.76 detected defects; under 50 lines, 1.48 (preprint) | [SkillsBench v4](https://arxiv.org/abs/2602.12670); [Zhang et al.](https://arxiv.org/abs/2608.08453) |
| **Nobody checked it.** Self-written and untested | Skills the agent wrote for itself, with no human in the loop, scored 8.1, 11.3 and 11.5 points below no skill with Claude Code, Codex and Gemini CLI (preprint). An LLM-based detector, run over 238 public skills and checked against 53 hand-labelled files, found no validation step in 69% (preprint). Skills with explicit AI-generation markers average 38% more detected defects, an association, not proof of cause (preprint) | [SkillsBench v4](https://arxiv.org/abs/2602.12670); [Hong et al., Jul 2026](https://arxiv.org/abs/2607.01456); [Zhang et al.](https://arxiv.org/abs/2608.08453) |
| **Does nothing.** | Of 49 public software-engineering skills, 39 changed the pass rate by zero; 7 helped, 3 hurt (preprint) | [Han et al., SWE-Skills-Bench, Mar 2026](https://arxiv.org/abs/2603.15401) |

## Good: it fires, it's short, the fragile step is code

| marker | in practice | source |
|---|---|---|
| **The description says what, then when** | Third person, then "Use when..." with the words people type. Key use case first: Claude Code cuts the description at 1,536 characters in its listing | [Anthropic best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) (vendor); [Claude Code docs](https://code.claude.com/docs/en/skills) (vendor); [agentskills.io](https://agentskills.io/skill-creation/optimizing-descriptions) |
| **The description doesn't list the steps** | A description that summarized the workflow made an agent do one review where the skill said two (anecdote, no controlled study) | [superpowers writing-skills](https://github.com/obra/superpowers/blob/main/skills/writing-skills/references/discovery.md) (practitioner) |
| **Short, with defaults, not menus** | "Would the agent get this wrong without this instruction? If the answer is no, cut it." Pick one tool and name one escape hatch | [agentskills.io best practices](https://agentskills.io/skill-creation/best-practices); [Anthropic best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) (vendor) |
| **Fragile steps get code** | Exact work (counts, sorting, deletions) is a script with JSON output; open-ended work stays prose. Then validate, fix, repeat | [Anthropic best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) (vendor); [agentskills.io best practices](https://agentskills.io/skill-creation/best-practices) |
| **Explains why instead of shouting** | All-caps ALWAYS or NEVER is "a yellow flag"; reframe and give the reason | [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) (vendor) |

## Great: what only you know, where it stops, proof it helps

| marker | in practice | source |
|---|---|---|
| **Gotchas from real failures, near the top** | "The highest-value content in many skills is a list of gotchas"; "the highest-signal content in any skill is the Gotchas section." Claude Code keeps only the first 5,000 tokens of a skill after compaction, so put them early. Hong et al.'s detector found buried gotchas in 81% of 238 skills (preprint) | [agentskills.io best practices](https://agentskills.io/skill-creation/best-practices); [Shihipar (Anthropic), Jun 2026](https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills) (vendor); [Claude Code docs](https://code.claude.com/docs/en/skills); [Hong et al.](https://arxiv.org/abs/2607.01456) |
| **Says where it stops** | A "Not for" line and a simpler fallback. Expert-curated skills still hurt 13 of 87 SkillsBench tasks; the common cause was one "correct" pipeline with no applicability boundary or lightweight fallback (preprint). A rule that must hold every time belongs in a hook, not prose | [SkillsBench v4](https://arxiv.org/abs/2602.12670); [Claude Code docs](https://code.claude.com/docs/en/skills) (vendor) |
| **Tested with and without, on every model** | The same skill helped one model and harness and hurt another on 36.78% of SkillsBench tasks (preprint). Run three or more prompts with and without the skill on each model you use, plus about 20 trigger queries. Steps and a scorer: [`evals/README.md`](../evals/README.md) | [Cheng et al., Oct 2026](https://arxiv.org/abs/2610.08875); [Anthropic best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) (vendor) |
| **Trigger tests with near-misses** | About 20 queries: half should trigger, half are near-misses that share words but need something else | [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) (vendor); [agentskills.io](https://agentskills.io/skill-creation/optimizing-descriptions) |
| **Retired when it's no longer needed** | Mainly for capability-uplift skills: if a new model passes the evals without the skill, "The skill isn't broken; it's just no longer necessary." | [Anthropic, Mar 2026](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills) (vendor) |

## The library

| marker | evidence | source |
|---|---|---|
| **Few skills, unique names** | A similar co-installed skill takes about 1 in 5 runs, and the final reply names the substitute in 0.9% of them (preprint) | [Yan et al., Oct 2026](https://arxiv.org/abs/2610.11647) |
| **Always-on knowledge goes in AGENTS.md** | In one vendor eval, an AGENTS.md docs index scored 100% against 53% for the skill; skills suit explicitly triggered workflows | [Vercel, Jan 2026](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) (vendor, one eval suite) |

## What the linter checks

`python3 skills/skill-review/scripts/lint_skill.py <skill_dir>` scores the mechanical rows out of 10:

| check | tier | points |
|---|---|---|
| description has a "use when" clause | poor | 2 |
| description length and form (40 to 1,024 characters, third person, leads with the job) | poor / good | 1 |
| description doesn't summarize the steps ("then", "first", "step", or a list of three actions) | good | 0.5 |
| body length (over 500 lines fails; over 150 is a "check") | poor / good | 0.5 |
| all-caps MUST/NEVER/ALWAYS, option buffets, file references, time-sensitive phrases, risky patterns and paths | good | 0.2 each |
| a Gotchas section, near the top | great | 1.5 |
| a "Not for" / "Don't use" boundary | great | 1 |
| a check or validation step | good | 1.5 |
| evals nearby (`evals/<name>/` in the repo, or tests in the folder) | great | 1 |

A risky pattern caps the score at 3. A score of 8.5 or more reads as great, 5 or more as good. The score is a floor: the script sees that a Gotchas heading exists, not whether its items are real. That's the model's job in the `skill-review` skill, and yours.
