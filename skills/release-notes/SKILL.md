---
name: release-notes
description: Drafts release notes for one version from a git log export or a list of merged changes. Use when the user asks for release notes, a changelog entry, "what's new in" a version, or notes for a version bump or tag.
---

# Release notes

Turns the commits between two tags into the release notes users read on the releases page.

Not for: marketing announcements or blog posts, security advisories (those need a CVE, affected versions and a disclosure process), or summarizing a single pull request. Say so and stop if that is the request.

## Gotchas

- **A revert cancels an earlier entry.** `Revert "feat: x"` or `revert: feat: x` means neither line ships. The script pairs them and lists the pair under `reverted`. If a revert's target isn't in the range, it undoes something already released: keep it and say so.
- **Squash merges: the title is the change.** The bullet list in a squash commit's body is the PR's history (`* fix typo`), not separate changes. Don't list those bullets.
- **BREAKING CHANGE can hide in the body footer**, not only as `feat!:` in the title. The script reads both. A breaking entry with no migration note is a problem to raise, not to fill in.
- **Bots are not contributors.** dependabot, renovate and github-actions commits are dropped; never thank them by name.
- **The version header must match the tag.** Use the version the user gives (or the tag name without the leading `v`). Never bump it yourself.
- **PR numbers come only from the JSON.** If an entry has `"pr": null`, write the entry without one.

## Steps

1. Get the change list. If the user gives a file or pasted text, use it. If they give two tags in a repo, export it:
   `git log <previous-tag>..<new-tag> > changes.txt`
   If you don't know the version, ask for it.
2. Group the changes. Do not sort or count commits yourself:
   `python3 scripts/group_changes.py changes.txt --version <version>`
   It prints JSON: `breaking`, `features`, `fixes`, `other`, `reverted`, `dropped` (chore, ci, merge, bot and dependency noise, as counts), `contributors` (bots removed) and `problems`.
3. Fill `templates/notes.md` from the JSON. Rewrite each description for a user (what they can now do, or what no longer goes wrong), but don't add facts the commit doesn't state.
4. If `problems` is not empty, list each one under the draft as a question for the user. Don't guess what a malformed line meant.

## Check before you answer

- [ ] every entry traces to one item in the script's JSON, and every JSON item in breaking, features and fixes is in the notes
- [ ] breaking changes come first, each with a migration step from `breaking_note` (or a question if it has none)
- [ ] no reverted change appears, and no PR number appears that isn't in the JSON
- [ ] the header version matches the version passed to the script
- [ ] contributors are the JSON's list, with no bots

If a check fails, fix the draft and check again.

## Output

Return the notes as Markdown, then the open questions. Don't tag, publish or post anything; a person reviews the notes first.
