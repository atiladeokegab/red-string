"""The holdout is enforced in the workflow, not just defined: every module that lists folders
applies the split, the runner labels which set it ran, and tuning only ever sees practice."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_cases  # noqa: E402
import tune  # noqa: E402

SAMPLE = ROOT / "cases" / "sample"  # 004 is its one holdout case
LISTING = {"iterdir", "glob", "rglob", "listdir", "scandir", "walk"}
GUARDS = {"tuning_cases", "is_holdout"}
# A module here lists folders without applying the split; each says why that is safe.
EXEMPT = {"starter/eval/holdout.py": "defines the split"}


def called(path: Path) -> set[str]:
    calls = (n.func for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.Call))
    return {f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "") for f in calls}


def test_every_module_that_lists_folders_applies_the_holdout():
    modules = [*(ROOT / "starter").rglob("*.py"), *(ROOT / "scripts").glob("*.py")]
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in sorted(modules)
        if called(p) & LISTING
        and not called(p) & GUARDS
        and p.relative_to(ROOT).as_posix() not in EXEMPT
    ]
    assert offenders == []


def answered(out: Path) -> tuple[list[str], str]:
    return sorted(p.name for p in out.iterdir() if p.is_dir()), (out / "SET").read_text()


def test_each_set_runs_its_own_cases_and_labels_its_output(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "store.json"))
    for which, expected in [
        ("practice", ["001", "002", "003", "005"]),
        ("holdout", ["004"]),
        ("all", ["001", "002", "003", "004", "005"]),
    ]:
        out = tmp_path / which
        assert run_cases.main([str(SAMPLE), "--out", str(out), "--set", which]) == 0
        assert answered(out) == (expected, f"{which}\n")
    assert run_cases.main([str(SAMPLE), "--out", str(tmp_path / "default")]) == 0
    assert answered(tmp_path / "default")[1] == "all\n"


def test_tuning_only_ever_sees_practice_cases(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "store.json"))
    assert tune.main([str(SAMPLE), "--out", str(tmp_path / "TUNING")]) == 0
    assert answered(tmp_path / "TUNING") == (["001", "002", "003", "005"], "practice\n")
