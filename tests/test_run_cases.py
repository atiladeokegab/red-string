import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_cases  # noqa: E402

from starter.agent import loop  # noqa: E402
from starter.agent.loop import AgentResult, step  # noqa: E402
from starter.core.errors import CaseCancelled  # noqa: E402
from starter.core.store import open_store  # noqa: E402


def test_sample_cases_write_five_answers_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "store.json"))
    assert run_cases.main([str(ROOT / "cases" / "sample"), "--out", str(tmp_path / "ANSWERS")]) == 0
    answers = sorted(p.name for p in (tmp_path / "ANSWERS").iterdir() if p.is_dir())
    assert answers == ["001", "002", "003", "004", "005"]
    index = (tmp_path / "ANSWERS" / "README.md").read_text()
    assert index.startswith("# Answers (all cases)")
    for name in answers:
        assert f"| {name} | DONE | 1 | 0 | fake | FakeProvider (no ANTHROPIC_API_KEY)" in index
    for name in answers:
        folder = tmp_path / "ANSWERS" / name
        files = {"ANSWER.md", "REASONING.md", "trace.jsonl", "spans.jsonl"}
        assert {p.name for p in folder.iterdir()} == files
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


def write_states(answers: Path, label: str, states: dict[str, str]) -> Path:
    """A fake run_cases output folder: a SET label and one ANSWER.md per case."""
    answers.mkdir(parents=True)
    (answers / "SET").write_text(f"{label}\n")
    for case_id, state in states.items():
        (answers / case_id).mkdir()
        (answers / case_id / "ANSWER.md").write_text(f"# Answer\n\nFinal state: {state}\n")
    return answers


# 004 and 011 hash into the holdout; 001, 002, 003 and 005 are practice
MIXED = {"001": "DONE", "002": "NEEDS_INFO", "003": "DONE", "005": "NEEDS_INFO"}


def compare(tmp_path, practice: dict, holdout: dict, labels=("practice", "holdout")) -> int:
    p = write_states(tmp_path / "P", labels[0], practice)
    h = write_states(tmp_path / "H", labels[1], holdout)
    return run_cases.main(["--compare", str(p), str(h)])


def test_compare_passes_when_holdout_and_practice_mix_match(tmp_path, capsys):
    assert compare(tmp_path, MIXED, {"004": "DONE", "011": "NEEDS_INFO"}) == 0
    out = capsys.readouterr().out
    assert "holdout" in out and "practice" in out
    assert "DONE" in out and "50%" in out and "shift" not in out


def test_compare_exits_2_when_a_state_share_moves_more_than_20_points(tmp_path, capsys):
    practice = dict.fromkeys(MIXED, "DONE")
    assert compare(tmp_path, practice, {"004": "ESCALATED", "011": "DONE"}) == 2
    escalated = next(line for line in capsys.readouterr().out.splitlines() if "ESCALATED" in line)
    assert "50%" in escalated and "0%" in escalated and "shift" in escalated


def test_compare_fails_closed_unless_each_side_is_its_own_labelled_set(tmp_path, capsys):
    assert compare(tmp_path / "a", MIXED, {"004": "DONE"}, labels=("all", "holdout")) == 2
    assert "not a --set practice run" in capsys.readouterr().out
    assert compare(tmp_path / "b", MIXED | {"004": "DONE"}, {"011": "DONE"}) == 2
    assert "case 004" in capsys.readouterr().out
    assert compare(tmp_path / "c", MIXED, {}) == 2
    assert "no holdout cases" in capsys.readouterr().out


def test_index_has_one_row_per_case_and_shows_the_question_asked(tmp_path):
    claude = step("model_input", provider="claude")
    fake = step("model_input", provider="fake")
    results = {
        "001": AgentResult(
            "Refunded one payment | ref 42.\nEmailed Priya.",
            "DONE",
            "",
            trace=[claude, step("tool_call", "send_message", "SIMULATED"), step("final")],
        ),
        "002": AgentResult(
            "I checked the account.\nCan you confirm your date of birth?",
            "NEEDS_INFO",
            "",
            trace=[fake, step("tool_call", "send_message", "ERROR", "bad"), step("final")],
        ),
        "003": AgentResult("Run failed:", "ERROR", "", trace=[step("final", status="ERROR")]),
    }
    run_cases.write_index(tmp_path, results, "holdout")
    lines = (tmp_path / "README.md").read_text().splitlines()
    assert lines[0] == "# Answers (holdout cases)"
    assert "| Case | Final state | Tool calls | Tool errors | Path | Answer |" in lines
    rows = [line for line in lines if line.startswith("| 00")]
    assert rows == [
        "| 001 | DONE | 1 | 0 | live | Refunded one payment \\| ref 42. |",
        "| 002 | NEEDS_INFO | 1 | 1 | fake | Can you confirm your date of birth? |",
        "| 003 | ERROR | 0 | 0 | none | Run failed: |",
    ]


def test_each_answer_has_spans_in_the_same_trace_as_its_steps(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "store.json"))
    assert run_cases.main([str(ROOT / "cases" / "sample"), "--out", str(tmp_path / "A")]) == 0
    folder = tmp_path / "A" / "001"
    trace = [json.loads(x) for x in (folder / "trace.jsonl").read_text().splitlines()]
    spans = [json.loads(x) for x in (folder / "spans.jsonl").read_text().splitlines()]
    trace_id = trace[0]["trace_id"]
    assert len(trace_id) == 32 and trace[-1]["trace_id"] == trace_id
    assert {s["trace_id"] for s in spans} == {trace_id}
    assert {s["name"] for s in spans} == {"case", "model", "gateway.call"}


def test_the_runner_uses_the_store_and_effects_mode_the_settings_name(tmp_path, monkeypatch):
    opened, modes = [], []
    local, build = run_cases.open_store, run_cases.build_gateway
    monkeypatch.setattr(
        run_cases, "open_store", lambda path: opened.append(path) or local(str(tmp_path / "s"))
    )
    monkeypatch.setattr(
        run_cases, "build_gateway", lambda store, effects: modes.append(effects) or build(store)
    )
    monkeypatch.setenv("DATA_PATH", "gs://bucket/store.json")
    monkeypatch.setenv("EFFECTS", "live")
    sample = str(ROOT / "cases" / "sample")
    assert run_cases.main([sample, "--out", str(tmp_path / "A"), "--set", "holdout"]) == 0
    assert (opened, modes) == (["gs://bucket/store.json"], ["live"])


def test_a_timed_out_case_is_cancelled_and_its_late_tool_call_never_lands(tmp_path, monkeypatch):
    release, finished = threading.Event(), threading.Event()
    late: list[Exception] = []
    given: dict = {}

    class Late(loop.FakeProvider):
        def run(self, system, messages, tools, trace, seconds_left):
            release.wait(5)  # still working when the runner gives up on the case
            try:
                next(t for t in tools if t.name == "send_message").call({"to": "x", "body": "late"})
            except Exception as exc:
                late.append(exc)
            finished.set()
            return "STATE: DONE", ""

    def spy(*args, **kwargs):
        given.update(kwargs)
        return loop.run(*args, **kwargs)

    monkeypatch.setattr(loop, "FakeProvider", Late)
    monkeypatch.setattr(run_cases, "run", spy)
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("CASE_TIMEOUT_S", "0.5")
    monkeypatch.setenv("MODEL_TIMEOUT_S", "0.1")
    (tmp_path / "cases" / "a").mkdir(parents=True)
    (tmp_path / "cases" / "a" / "index.md").write_text("# a")
    assert run_cases.main([str(tmp_path / "cases"), "--out", str(tmp_path / "out")]) == 1
    assert given["cancel"].is_set()  # the runner told the case it gave up on to stop
    assert given["deadline"] <= time.monotonic()  # and gave it the same budget it enforced
    release.set()
    assert finished.wait(5)
    assert [(type(exc), str(exc)) for exc in late] == [(CaseCancelled, "case cancelled")]
    events = open_store(str(tmp_path / "store.json")).snapshot()["events"]
    assert [e for e in events if e["type"] == "tool_call"] == []
