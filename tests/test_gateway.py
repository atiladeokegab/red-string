import pytest

from starter.core.errors import NotFound
from starter.core.gateway import Gateway, build_gateway


def test_effect_tool_is_simulated_and_audited_for_any_case(store):
    gateway = build_gateway(store)
    result = gateway.call("send_message", {"to": "ann", "body": "hi"}, case_id="any-case-42")
    assert result == {"status": "SIMULATED", "payload": {"to": "ann", "body": "hi"}}
    [event] = store.snapshot()["events"]
    assert (event["type"], event["case_id"], event["tool"]) == (
        "tool_call",
        "any-case-42",
        "send_message",
    )


def test_read_tool_is_ok_not_simulated(store):
    gateway = build_gateway(store)
    assert gateway.call("list_items", {}, case_id="c1")["status"] == "OK"


def test_bad_args_raise_value_error_and_are_not_audited(store):
    gateway = build_gateway(store)
    with pytest.raises(ValueError):
        gateway.call("send_message", {"to": "ann"}, case_id="c1")
    with pytest.raises(ValueError):
        gateway.call("send_message", {"to": "ann", "body": "hi", "cc": "bob"}, case_id="c1")
    with pytest.raises(NotFound):
        gateway.call("launch_rocket", {}, case_id="c1")
    assert store.snapshot()["events"] == []


def test_register_reads_type_hints(store):
    gateway = Gateway(store)

    @gateway.register
    def refund(amount: int) -> dict:
        """Refund an amount."""
        return {"amount": amount}

    assert gateway.call("refund", {"amount": "5"}, "c1")["payload"] == {"amount": 5}
    with pytest.raises(ValueError):
        gateway.call("refund", {"amount": "five"}, "c1")


def test_api_maps_bad_args_to_422_and_needs_login(client, auth):
    good = {"case_id": "c1", "args": {"to": "ann", "body": "hi"}}
    assert client.post("/api/tools/send_message", json=good).status_code == 401
    r = client.post("/api/tools/send_message", json=good, headers=auth)
    assert (r.status_code, r.json()["status"]) == (200, "SIMULATED")
    bad = {"case_id": "c1", "args": {"to": "ann"}}
    assert client.post("/api/tools/send_message", json=bad, headers=auth).status_code == 422
    assert client.post("/api/tools/nope", json=good, headers=auth).status_code == 404
