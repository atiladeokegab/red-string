import json
import sys
import threading
from pathlib import Path

import pytest

from starter.agent import loop
from starter.runtime.config import Settings

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import run_cases  # noqa: E402


def test_timeouts_default_and_come_from_env():
    s = Settings.from_env({})
    assert (s.case_timeout_s, s.model_timeout_s) == (120, 50)
    s = Settings.from_env({"CASE_TIMEOUT_S": "30", "MODEL_TIMEOUT_S": "10"})
    assert (s.case_timeout_s, s.model_timeout_s) == (30, 10)


def test_model_timeout_with_its_retry_must_fit_inside_the_case_timeout():
    Settings.from_env({"CASE_TIMEOUT_S": "120", "MODEL_TIMEOUT_S": "50"})
    with pytest.raises(ValueError, match="inner timeouts must be shorter than the case timeout"):
        Settings.from_env({"CASE_TIMEOUT_S": "120", "MODEL_TIMEOUT_S": "60"})


def test_claude_client_gets_the_model_timeout_and_one_retry():
    client = loop.ClaudeProvider(Settings(anthropic_api_key="test-key", model_timeout_s=7)).client
    assert (client.timeout, client.max_retries) == (7, 1)


def test_a_hung_case_times_out_and_the_next_case_still_runs(tmp_path, monkeypatch):
    release = threading.Event()

    class Hanging(loop.FakeProvider):
        def run(self, system, messages, tools, trace, seconds_left):
            if messages[0]["content"].startswith("Case a"):
                release.wait(5)  # a model call that never comes back in time
            return super().run(system, messages, tools, trace, seconds_left)

    monkeypatch.setattr(loop, "FakeProvider", Hanging)
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("CASE_TIMEOUT_S", "0.5")
    monkeypatch.setenv("MODEL_TIMEOUT_S", "0.1")
    cases = tmp_path / "cases"
    for name in ("a", "b"):
        (cases / name).mkdir(parents=True)
        (cases / name / "index.md").write_text(f"# {name}")
    try:
        assert run_cases.main([str(cases), "--out", str(tmp_path / "out")]) == 1
    finally:
        release.set()

    a = tmp_path / "out" / "a"
    assert "Final state: ERROR" in (a / "ANSWER.md").read_text()
    assert "case timeout after 0.5s" in (a / "REASONING.md").read_text()
    [final] = [json.loads(x) for x in (a / "trace.jsonl").read_text().splitlines()]
    assert (final["tool"], final["status"], final["error"]) == (
        None,
        "ERROR",
        "case timeout after 0.5s",
    )
    assert "Final state: DONE" in (tmp_path / "out" / "b" / "ANSWER.md").read_text()


def test_a_timed_out_case_cannot_act_afterwards(tmp_path, monkeypatch):
    release, finished = threading.Event(), threading.Event()

    class Late(loop.FakeProvider):
        def run(self, system, messages, tools, trace, seconds_left):
            if not messages[0]["content"].startswith("Case a"):
                return super().run(system, messages, tools, trace, seconds_left)
            try:
                release.wait(5)  # still busy when the runner gives up on case a
                return super().run(system, messages, tools, trace, seconds_left)
            finally:
                finished.set()

    monkeypatch.setattr(loop, "FakeProvider", Late)
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("CASE_TIMEOUT_S", "0.5")
    monkeypatch.setenv("MODEL_TIMEOUT_S", "0.1")
    cases = tmp_path / "cases"
    for name in ("a", "b"):
        (cases / name).mkdir(parents=True)
        (cases / name / "index.md").write_text(f"# {name}")
    assert run_cases.main([str(cases), "--out", str(tmp_path / "out")]) == 1
    release.set()
    assert finished.wait(5)  # case a's thread woke up and tried to send its message

    events = json.loads((tmp_path / "store.json").read_text())["events"]
    assert [e["case_id"] for e in events if e["type"] == "tool_call"] == ["b"]
