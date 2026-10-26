---
name: release-notes
description: Drafts release notes for one version from a git log export or a list of merged changes. Use when the user asks for release notes, a changelog entry, or "what's new in" a version.
---

# Release notes

## Steps

1. Get the change list (a file, pasted text, or `git log <previous-tag>..<new-tag>`). Ask for the version if you don't know it.
2. Group the changes with the script instead of sorting them yourself:
   `python3 skills/release-notes/scripts/group_changes.py changes.txt --version <version>`
3. Write the notes from the JSON: breaking changes first, then features, fixes and other changes, each with its PR number.
4. Check before you answer: every entry comes from the JSON, and the header version matches the one you passed in. Fix and check again if not.
