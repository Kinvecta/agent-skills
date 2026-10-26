# Poor, good, great: one skill at three levels

The same `release-notes` skill written three ways, for the video [*AI Agent Skills: What Makes One Actually Work*](https://youtu.be/6jsMh0dfNe8). Read them side by side; the differences are the lesson.

| level | file | lint score | what it adds |
|---|---|---|---|
| poor | [`release-notes/poor/SKILL.md`](release-notes/poor/SKILL.md) | 2.0 / 10 | nothing: a name and one vague line |
| good | [`release-notes/good/SKILL.md`](release-notes/good/SKILL.md) | 6.5 / 10 | a description that says what and when, short steps, a script for the grouping, a check step |
| great | [`release-notes/great/SKILL.md`](release-notes/great/SKILL.md) | 9.0 / 10 | gotchas from real failures, a "Not for" boundary, a full checklist (the installable copy, with its evals, scores 10) |

Scores come from [`skills/skill-review/scripts/lint_skill.py`](../../skills/skill-review/scripts/lint_skill.py):

```bash
python3 skills/skill-review/scripts/lint_skill.py examples/poor-good-great/release-notes/poor
```

These folders are for reading, not installing. They all use `name: release-notes`, which doesn't match their folder names, and the validator only checks `skills/`, so it ignores them. The good and great versions point at the script by its repo path (`skills/release-notes/scripts/group_changes.py`). The installable copy is [`skills/release-notes/`](../../skills/release-notes/), where the same line says `scripts/group_changes.py`.

## Poor: it never fires, and if it did, it adds nothing

```yaml
description: Writes release notes.
```

- **No "use when".** The description is the only thing the agent sees before it decides to load a skill, so it "carries the entire burden of triggering" [1]. In a scan of 138,133 public skills, 52.3% had no trigger guidance [2] (preprint). In one vendor eval, a skill was never invoked in 56% of eval cases [3].
- **Nothing the model doesn't already know.** "Write good release notes" is what it would do anyway. The test for each line is "Would the agent get this wrong without this instruction? If the answer is no, cut it" [1]. Of 49 public software-engineering skills, 39 changed the pass rate by zero [4] (preprint).
- **No check.** An LLM-based detector, run over 238 public skills and checked against 53 hand-labelled files, found no validation step in 69% [5] (preprint).

## Good: it fires, and the fragile step is code

```yaml
description: Drafts release notes for one version from a git log export or a list of merged
  changes. Use when the user asks for release notes, a changelog entry, or "what's new in" a version.
```

- **What, then when, in the words people type.** Third person, with the trigger words up front, because Claude Code cuts the listing at 1,536 characters [6], [7].
- **The description doesn't list the steps.** Jesse Vincent's Superpowers project documents a case where a description summarizing the workflow made the agent follow the summary and do one review where the skill said two [8] (anecdote, no controlled study).
- **Grouping commits is a script, not prose.** Sorting and matching are fragile and exact: "narrow bridge" work that gets code, not a suggestion [7]. The script prints JSON the model fills a template from.
- **A check before it answers.** "Run validator, fix errors, repeat" [7].
- **Short.** The body is 9 lines. In SkillsBench v4, tasks with compact and standard skills gained 19.0 and 21.5 points; the few with comprehensive ones (5 tasks) gained 0.7 [9] (preprint). That compares different tasks, so it's a correlation, not proof that length alone hurts.

## Great: what only you know, where it stops, and proof it helps

- **Gotchas from real failures, near the top.** Reverts that cancel an earlier entry, squash-merge bodies, a BREAKING CHANGE footer in the body, bots in the contributor list, a header that doesn't match the tag. Gotchas are "the highest-value content in many skills" [1] and "the highest-signal content in any skill" [10]. They go near the top because Claude Code keeps only the first 5,000 tokens of a skill after compaction [6]. The same study's detector found buried gotchas in 81% of 238 skills [5] (preprint).
- **A "Not for" line.** Marketing posts, security advisories and single-PR summaries share words with release notes but need something else. In SkillsBench v4, expert-curated skills still hurt 13 of 87 tasks; the common cause was one "correct" pipeline with no applicability boundary or lightweight fallback [9] (preprint). When a similar skill is installed alongside, it takes about 1 in 5 runs [11] (preprint), and recall of the right skill fell from 73.6% to 27.4% as unrelated skills grew to 1,000 [12] (preprint).
- **A checklist tied to the script's output**: every entry traces to the JSON, breaking changes first with a migration step, no invented PR numbers.
- **Tested with and without, and on trigger queries.** [`evals/release-notes/`](../../evals/release-notes/) has three output prompts, 20 trigger queries (10 should, 10 near-miss) and pytest for the script. Anthropic's skill-creator uses about 20 queries, half should-trigger, half near-misses [13]. The same skill helped one model and harness and hurt another on 36.78% of SkillsBench tasks [14] (preprint), so run the tests on every model you use. For capability-uplift skills, when a new model passes without the skill, "The skill isn't broken; it's just no longer necessary" [15].

## Try it

1. Run [`skills/skill-review/`](../../skills/skill-review/)'s linter on one of your own skills.
2. Rewrite the description: what it does, then "Use when..." with the words people type.
3. Run three prompts with and without the skill and about 20 trigger queries, record them in a results sheet and score them with `tools/eval_report.py` (steps in [`evals/README.md`](../../evals/README.md); copy the format of [`evals/release-notes/`](../../evals/release-notes/)). To see the levels differ, run the tricky case 3 against each of the three versions.
4. Add one gotcha from a mistake you had to correct.

The full rubric, with sources, is in [`docs/skill-quality.md`](../../docs/skill-quality.md).

## Sources

Preprints are not peer-reviewed. "Vendor" means a company evaluating its own product or guidance.

1. agentskills.io, [Best practices for skill creators](https://agentskills.io/skill-creation/best-practices) and [Optimizing skill descriptions](https://agentskills.io/skill-creation/optimizing-descriptions)
2. Zhang et al., [What Keeps Agent Skills from Being Reusable? Evidence from 138K SKILL.md Files](https://arxiv.org/abs/2608.08453), Aug 2026 (preprint)
3. Gao (Vercel), [AGENTS.md outperforms skills in our agent evals](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals), Jan 2026 (vendor, one eval suite)
4. Han et al., [SWE-Skills-Bench: Do Agent Skills Actually Help in Real-World Software Engineering?](https://arxiv.org/abs/2603.15401), Mar 2026 (preprint)
5. Hong et al., [From Anatomy to Smells: An Empirical Study of SKILL.md in Agent Skills](https://arxiv.org/abs/2607.01456), Jul 2026 (preprint)
6. Claude Code docs, [Skills](https://code.claude.com/docs/en/skills) (vendor docs)
7. Anthropic, [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) (vendor docs)
8. Vincent / Prime Radiant, superpowers [writing-skills, references/discovery.md](https://github.com/obra/superpowers/blob/main/skills/writing-skills/references/discovery.md) (practitioner, anecdote)
9. Li et al., [SkillsBench](https://arxiv.org/abs/2602.12670), v4, Jun 2026 (preprint)
10. Shihipar (Anthropic), [Lessons from building Claude Code: How we use skills](https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills), Jun 2026 (vendor)
11. Yan et al., [One Skill Too Many: How Co-Installed Skills Conflict in Coding Agents](https://arxiv.org/abs/2610.11647), Oct 2026 (preprint)
12. Liu et al., [Lost in Implicit Routing: How LLM Agents Fail to Load Relevant Skills at Scale](https://arxiv.org/abs/2610.18522), Oct 2026 (preprint)
13. Anthropic, [skill-creator SKILL.md](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) (vendor)
14. Cheng et al., [An Empirical Study of Agent Skills' Downstream Utility](https://arxiv.org/abs/2610.08875), Oct 2026 (preprint)
15. Anthropic, [Improving skill-creator: test, measure, and refine Agent Skills](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills), Mar 2026 (vendor)
