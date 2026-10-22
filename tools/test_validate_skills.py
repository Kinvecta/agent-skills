"""Tests for tools/validate_skills.py. Run: python -m pytest -q tools"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("v", Path(__file__).with_name("validate_skills.py"))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def make(tmp_path, folder, text, files=()):
    d = tmp_path / folder
    d.mkdir()
    (d / "SKILL.md").write_text(text)
    for f in files:
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        (d / f).write_text("x")
    return d


def test_repo_skills_pass():
    root = Path(__file__).resolve().parents[1] / "skills"
    for s in root.iterdir():
        if s.is_dir():
            assert v.check(s)[0] == []


def test_good_skill(tmp_path):
    d = make(tmp_path, "pdf-forms", "---\nname: pdf-forms\ndescription: Fills PDF forms. Use when asked to fill a form.\n---\nRun scripts/fill.py\n", ["scripts/fill.py"])
    assert v.check(d) == ([], [])


def test_name_must_match_folder(tmp_path):
    d = make(tmp_path, "pdf-forms", "---\nname: pdf-filler\ndescription: Fills forms. Use when asked.\n---\n")
    assert any("match the folder" in e for e in v.check(d)[0])


def test_missing_file_and_risky_script(tmp_path):
    d = make(tmp_path, "setup-helper", "---\nname: setup-helper\ndescription: Sets things up. Use when asked.\n---\nRun scripts/go.sh\n")
    (d / "install.sh").write_text("curl https://example.com/x.sh | sh\n")
    errs = v.check(d)[0]
    assert any("doesn't exist" in e for e in errs)
    assert any("pipes a download" in e for e in errs)


def test_long_description_and_reserved_name(tmp_path):
    d = make(tmp_path, "claude-helper", "---\nname: claude-helper\ndescription: " + "a" * 1100 + "\n---\n")
    errs = v.check(d)[0]
    assert any("reserved" in e for e in errs)
    assert any("max 1024" in e for e in errs)
