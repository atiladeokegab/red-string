"""ANSWER.md counts side effects from the gateway's audit, not from what the answer says."""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_cases  # noqa: E402

from starter.agent import loop  # noqa: E402
from starter.eval.effects import claim_mismatches, count_effects, effects_line  # noqa: E402


class Boaster:
    """Sends one message and claims two."""

    name = "test"

    def run(self, system, messages, tools, trace, seconds_left):
        send = next(t for t in tools if t.name == "send_message")
        send.call({"to": "ann", "body": "Your refund is on its way."})
        return "I sent 2 messages to the customer.\nSTATE: DONE", ""


def test_answer_shows_the_audited_count_not_the_claimed_one(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "store.json"))
    monkeypatch.setattr(run_cases, "run", lambda c, g, s, **kw: loop.run(c, g, s, Boaster(), **kw))
    (tmp_path / "cases" / "c1").mkdir(parents=True)
    (tmp_path / "cases" / "c1" / "index.md").write_text("# Refund\n\nPlease refund me.")
    for run_no in (1, 2):  # a second run over the same store counts only its own effects
        out = tmp_path / f"out{run_no}"
        assert run_cases.main([str(tmp_path / "cases"), "--out", str(out)]) == 0
        answer = (out / "c1" / "ANSWER.md").read_text()
        assert "\nEffects: 1 (send_message: 1)\n" in answer
        assert (
            "Effects mismatch: the answer claims 2 send_message, the gateway recorded 1" in answer
        )


def test_count_skips_reads_repeats_and_other_cases():
    effects = {"send_message": True, "send_email": True, "list_items": False}
    events = [
        {"type": "tool_call", "case_id": "c1", "tool": "send_email"},
        {"type": "tool_call", "case_id": "c1", "tool": "send_email", "repeat": True},
        {"type": "tool_call", "case_id": "c1", "tool": "list_items"},
        {"type": "tool_call", "case_id": "c2", "tool": "send_message"},
        {"type": "tool_call", "case_id": "c1", "tool": "send_message"},
        {"type": "tool_call", "case_id": "c1", "tool": "send_message"},
        {"type": "note", "case_id": "c1"},
    ]
    counts = count_effects(events, "c1", effects)
    assert effects_line(counts) == "Effects: 3 (send_email: 1, send_message: 2)"
    assert effects_line(count_effects([], "c1", effects)) == "Effects: 0"
    assert claim_mismatches("Sent one email and two messages.", counts, effects) == []
    assert claim_mismatches("I emailed them 3 emails.", counts, effects) == [
        "the answer claims 3 send_email, the gateway recorded 1"
    ]
