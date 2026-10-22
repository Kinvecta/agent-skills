# Security policy

## Status

This repository holds example Agent Skills that accompany Kinvecta training videos. It is **not actively maintained**, has no supported versions and makes no security guarantees. Review and scan anything you reuse.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private reporting instead: go to the **Security** tab and choose **Report a vulnerability**. Reports are read on a best-effort basis, with no response or fix timeline.

## A skill is software

A skill runs with the permissions of the agent that loads it: its shell, its files and any credentials it can reach. Before you install any skill, from here or anywhere else:

1. **Read every file**, not just `SKILL.md`. Look for network calls, downloads piped into a shell, encoded payloads and instructions to ignore rules.
2. **Scan the scripts** with the tools your organization already uses.
3. **Pin the version.** Install from a tag or a commit, not a moving branch, and keep your own approved copy.
4. **Run it in a sandbox** (a container or a throwaway environment) before it touches real data.
5. **Approve changes.** If an agent edits a skill, a person reviews the change before it's used again.

## What the repository does to lower risk

- Every skill is checked by `tools/validate_skills.py` on every push: format, file references, and patterns such as a download piped into a shell, run-time base64 decoding, absolute local paths and secret-like strings.
- Every push and pull request is checked with a Gitleaks scan of the full history. No secrets, credentials or personal data are committed.
- CodeQL scans the Python on every push and weekly. Dependabot keeps the GitHub Actions current.
- Third-party GitHub Actions are pinned to full commit SHAs, and workflows run with read-only tokens.

Passing checks lower the risk but do not prove a skill is safe.
