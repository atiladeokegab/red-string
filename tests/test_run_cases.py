import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_cases  # noqa: E402


def test_sample_cases_write_five_answers_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "store.json"))
    assert run_cases.main([str(ROOT / "cases" / "sample"), "--out", str(tmp_path / "ANSWERS")]) == 0
    answers = sorted(p.name for p in (tmp_path / "ANSWERS").iterdir() if p.is_dir())
    assert answers == ["001", "002", "003", "004", "005"]
    for name in answers:
        folder = tmp_path / "ANSWERS" / name
        assert {p.name for p in folder.iterdir()} == {"ANSWER.md", "REASONING.md", "trace.jsonl"}
        answer = (folder / "ANSWER.md").read_text()
        assert "Final state: DONE" in answer and "SIMULATED" in answer
        trace = (folder / "trace.jsonl").read_text()
        assert "OUTCOME_" not in trace
        for line in trace.splitlines():
            entry = json.loads(line)
            assert {"tool", "status", "error"} <= entry.keys()
            assert entry["status"] in {"SIMULATED", "OK", "ERROR"}


def test_a_failing_case_is_reported_and_the_rest_still_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "store.json"))
    cases = tmp_path / "cases"
    for name in ("a", "b"):
        (cases / name).mkdir(parents=True)
        (cases / name / "index.md").write_text(f"# {name}")
    (cases / "a" / "history.md").mkdir()  # reading it raises IsADirectoryError
    assert run_cases.main([str(cases), "--out", str(tmp_path / "out")]) == 1
    answer = (tmp_path / "out" / "a" / "ANSWER.md").read_text()
    assert "Final state: ERROR" in answer and "Run failed" in answer
    lines = (tmp_path / "out" / "a" / "trace.jsonl").read_text().splitlines()
    [final] = [json.loads(x) for x in lines]
    assert final["status"] == "ERROR" and final["error"].startswith("IsADirectoryError")
    assert (tmp_path / "out" / "b" / "trace.jsonl").exists()
