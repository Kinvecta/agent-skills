"""Tests for skills/release-notes/scripts/group_changes.py. Run: python -m pytest -q evals"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SCRIPT = HERE.parents[1] / "skills" / "release-notes" / "scripts" / "group_changes.py"


def run(args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True)


def group(name, version="1.4.0"):
    out = run([str(HERE / name), "--version", version])
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_normal_log_groups_and_drops_noise():
    r = group("git-log-1.4.0.txt")
    assert r["counts"] == {"breaking": 0, "features": 2, "fixes": 2, "other": 2}
    assert [e["pr"] for e in r["features"]] == [142, 138]
    assert [e["pr"] for e in r["fixes"]] == [140, 137]
    assert r["dropped"] == {"chore": 1, "ci": 1}
    assert r["contributors"] == ["Ana Ruiz", "Raj Patel", "Sam Okafor"]
    assert r["problems"] == []


def test_breaking_change_in_body_footer_and_bang():
    r = group("git-log-tricky.txt", "v2.0.0")
    assert r["version"] == "2.0.0"
    assert [e["pr"] for e in r["breaking"]] == [152, 146]
    assert r["breaking"][0]["breaking_note"] == (
        "tidy.ini is no longer read. Rename it to tidy.toml and run `tidy config migrate` once.")
    assert any("no migration note" in p for p in r["problems"])


def test_revert_cancels_the_original():
    r = group("git-log-tricky.txt", "2.0.0")
    assert [x["pr"] for x in r["reverted"]] == [151]
    listed = [e["pr"] for g in ("breaking", "features", "fixes", "other") for e in r[g]]
    assert 151 not in listed


def test_bots_squash_bullets_and_malformed_lines():
    r = group("git-log-tricky.txt", "2.0.0")
    assert not any("bot" in c.lower() for c in r["contributors"])
    assert r["dropped"] == {"deps": 2, "merge": 1}
    descriptions = [e["description"] for g in ("breaking", "features", "fixes", "other") for e in r[g]]
    assert "add toml loader" not in descriptions  # squash body bullet, not a change
    assert any("feat(api add pagination" in p for p in r["problems"])


def test_one_line_input_from_stdin():
    text = "- feat(ui): dark mode (#9)\n- fix: crash on empty file\nUpdate README\nrevert: feat(ui): dark mode\n"
    out = run(["-", "--version", "0.2.0"], stdin=text)
    r = json.loads(out.stdout)
    assert r["features"] == [] and r["reverted"][0]["pr"] == 9
    assert [e["description"] for e in r["fixes"]] == ["crash on empty file"]
    assert any("Update README" in p for p in r["problems"])


def test_same_input_same_output():
    assert group("git-log-tricky.txt", "2.0.0") == group("git-log-tricky.txt", "2.0.0")


def test_bad_version_and_missing_file_fail_cleanly():
    bad = run([str(HERE / "git-log-1.4.0.txt"), "--version", "latest"])
    assert bad.returncode == 2 and "--version" in bad.stderr and bad.stdout == ""
    missing = run([str(HERE / "nope.txt"), "--version", "1.0.0"])
    assert missing.returncode == 1 and "can't read" in missing.stderr


def test_empty_input_is_a_problem_not_silence():
    r = json.loads(run(["-", "--version", "1.0.0"], stdin="").stdout)
    assert r["counts"] == {"breaking": 0, "features": 0, "fixes": 0, "other": 0}
    assert any("no changes found" in p for p in r["problems"])


def test_non_utf8_input_fails_cleanly(tmp_path):
    f = tmp_path / "log.txt"
    f.write_bytes(b"\xff\xfe feat: x\n")
    out = run([str(f), "--version", "1.0.0"])
    assert out.returncode == 1 and "not UTF-8" in out.stderr and "Traceback" not in out.stderr


def test_crlf_unicode_and_fuller_headers():
    log = ("commit 1111111111111111111111111111111111111111\r\n"
           "Author:     Zoë Núñez <z@example.com>\r\n"
           "AuthorDate: Mon Oct 19 09:30:12 2026 -0500\r\n"
           "Commit:     Zoë Núñez <z@example.com>\r\n"
           "CommitDate: Mon Oct 19 09:30:12 2026 -0500\r\n\r\n"
           "    feat!: drop Python 3.9 (#4)\r\n\r\n"
           "    BREAKING CHANGE: needs Python 3.10\r\n    or newer.\r\n    Signed-off-by: Zoë\r\n")
    r = json.loads(run(["-", "--version", "2.0.0"], stdin=log).stdout)
    assert r["problems"] == []
    assert r["breaking"][0]["breaking_note"] == "needs Python 3.10 or newer."
    assert r["contributors"] == ["Zoë Núñez"]


def test_bot_commits_are_dropped_even_without_a_conventional_type():
    log = ("commit 2222222\nAuthor: dependabot[bot] <x@example.com>\n\n    Bump lodash from 4.17.20 to 4.17.21 (#9)\n\n"
           "commit 3333333\nAuthor: renovate[bot] <x@example.com>\n\n    fix(deps): update dependency foo to v2 (#10)\n")
    r = json.loads(run(["-", "--version", "1.0.0"], stdin=log).stdout)
    assert r["fixes"] == [] and r["problems"] == [] and r["dropped"] == {"deps": 2}


def test_relanded_change_ships_and_only_the_older_one_is_reverted():
    # newest first, as git log prints it: the change landed (#1), was reverted, then landed again (#3)
    r = json.loads(run(["-", "--version", "1.0.0"], stdin="feat: x (#3)\nrevert: feat: x\nfeat: x (#1)\n").stdout)
    assert [e["pr"] for e in r["features"]] == [3]
    assert [x["pr"] for x in r["reverted"]] == [1]


def test_revert_of_a_revert_means_the_change_ships():
    for title in ('Reapply "feat(ui): dark mode (#7)" (#9)', 'Revert "Revert "feat(ui): dark mode (#7)"" (#9)'):
        log = (f"commit aaaaaaa\nAuthor: A <a@example.com>\n\n    {title}\n\n"
               "commit bbbbbbb\nAuthor: A <a@example.com>\n\n    Revert \"feat(ui): dark mode (#7)\" (#8)\n\n"
               "    This reverts commit ccccccc.\n\n"
               "commit ccccccc\nAuthor: A <a@example.com>\n\n    feat(ui): dark mode (#7)\n")
        r = json.loads(run(["-", "--version", "1.0.0"], stdin=log).stdout)
        assert [e["pr"] for e in r["features"]] == [7], title
        assert r["reverted"] == [] and r["other"] == [] and r["problems"] == [], title
