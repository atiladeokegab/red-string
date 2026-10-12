"""The answer key never reaches the model. A fixture case carries two planted strings in its
outcome sections; the loop's model input (trace[0], the exact system, messages and tools sent)
must contain neither. The leaky variant proves this test can go red."""

import json
from pathlib import Path

from starter.agent.cases import CASE_FILES, load_case
from starter.agent.loop import run
from starter.core.gateway import build_gateway
from starter.runtime.config import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "leaky_case"
PLANTED = ("FORBIDDEN_OUTCOME", "EXPECTED_NEXT")


def leaked(model_input: dict) -> list[str]:
    text = json.dumps(model_input)
    return [s for s in PLANTED if s in text]


def test_fixture_really_contains_the_planted_strings():
    raw = "".join((FIXTURE / name).read_text() for name in CASE_FILES)
    assert all(s in raw for s in PLANTED)


def test_outcome_never_reaches_the_model(store):
    result = run(load_case(FIXTURE), build_gateway(store), Settings())
    assert result.trace[0]["type"] == "model_input"
    assert leaked(result.trace[0]) == []


def test_leaky_loader_is_caught(store):
    raw = "\n\n".join((FIXTURE / name).read_text() for name in CASE_FILES)
    result = run({"id": FIXTURE.name, "body": raw}, build_gateway(store), Settings())
    assert leaked(result.trace[0]) == list(PLANTED)
