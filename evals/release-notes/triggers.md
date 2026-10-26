# Trigger tests for release-notes

Start a fresh session with only this skill installed (plus the ones you normally use), send each query, and record whether `release-notes` loaded. Run each query 3 times; a should-trigger query passes if it loads at least 2 of 3 times, a should-not query if it loads at most 1 of 3. The near-misses share words with the skill but need something else; they're the useful negatives (Anthropic's skill-creator suggests about 20 queries, half and half).

Record each run in the trigger rows of [`results-template.csv`](results-template.csv) (`result` = 1 if the skill loaded) and score with `python3 tools/eval_report.py evals/release-notes/results/<your-sheet>.csv`. Full steps: [`evals/README.md`](../README.md#step-5-trigger-tests).

## Should trigger (10)

1. Write the release notes for v1.4.0 from changes.txt
2. can you draft a changelog entry for 2.0.0, git log is pasted below
3. What's new in 3.1? Here are the merged PRs since the last tag
4. We're bumping the version to 1.5.0 tonight, I need the notes for the GitHub release
5. Turn this git log into release notes
6. Summarize the commits between v2.3.0 and v2.4.0 for the releases page
7. update CHANGELOG.md for the 0.9.0 release using these commits
8. I tagged v1.0.0, what should the release say?
9. Draft patch notes for 1.2.1 from this list of fixes
10. here's `git log v4.1.0..v4.2.0`, write it up for users

## Should not trigger (10 near-misses)

1. Write a blog post announcing v2 to our customers
2. Summarize this PR for the reviewer
3. Write a security advisory for the auth bypass fixed in 1.4.1
4. Write a commit message for my staged changes
5. Which version should this be, a minor or a patch? (versioning question, no notes)
6. Bump the version in package.json to 1.5.0
7. Explain what changed in this diff
8. Write a tweet about our new release
9. Draft the monthly status report from the tracker CSV
10. Set up semantic-release so the changelog is generated in CI
