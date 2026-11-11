"""The Parallel wrappers with HTTP mocked: request shapes, and 402/5xx degrading to the keyless MCP
or to Unavailable."""

import io
import json
import urllib.error

import pytest

from starter import parallel


def _fake(monkeypatch, *replies):
    """Serve replies in order (a dict, or an int HTTP error code); return the requests made."""
    sent, queue = [], list(replies)

    def urlopen(req, timeout):
        assert timeout  # every call is bounded
        body = json.loads(req.data) if req.data else None
        sent.append({"url": req.full_url, "body": body, "method": req.get_method()})
        reply = queue.pop(0)
        if isinstance(reply, int):
            raise urllib.error.HTTPError(req.full_url, reply, "no", {}, None)
        return io.BytesIO(json.dumps(reply).encode())

    monkeypatch.setattr(parallel.urllib.request, "urlopen", urlopen)
    return sent


def _mcp_reply(data: dict) -> dict:
    return {"result": {"content": [{"type": "text", "text": json.dumps(data)}]}}


PAGE = {"url": "https://noaa.gov/m", "excerpts": ["landfall on 20 September"], "full_content": "x"}


def test_extract_asks_the_keyed_api_for_a_live_fetch(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "k")
    sent = _fake(monkeypatch, {"results": [PAGE]})
    assert parallel.extract(["https://noaa.gov/m"], "landfall date") == [PAGE]
    assert sent[0]["url"] == "https://api.parallel.ai/v1/extract"
    assert sent[0]["body"]["advanced_settings"]["fetch_policy"] == {"max_age_seconds": 600}


@pytest.mark.parametrize("code", [402, 503])
def test_extract_and_search_fall_back_to_the_keyless_mcp_on_402_and_5xx(monkeypatch, code):
    monkeypatch.setenv("PARALLEL_API_KEY", "k")
    sent = _fake(monkeypatch, code, _mcp_reply({"results": [PAGE]}))
    assert parallel.extract(["https://noaa.gov/m"], "landfall date") == [PAGE]
    assert sent[1]["url"] == parallel.MCP
    assert sent[1]["body"]["params"]["name"] == "web_fetch"
    assert sent[1]["body"]["params"]["arguments"]["allow_live_fetch"] is True

    sent = _fake(monkeypatch, code, _mcp_reply({"results": [{"url": "u"}]}))
    assert parallel.search("o", ["q"]) == [{"url": "u"}]
    assert sent[1]["body"]["params"]["name"] == "web_search"


def test_a_client_error_is_not_degraded(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "k")
    _fake(monkeypatch, 422)
    with pytest.raises(urllib.error.HTTPError):
        parallel.extract(["u"], "o")


def test_keyed_only_endpoints_are_unavailable_without_a_key_or_on_402(monkeypatch):
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    sent = _fake(monkeypatch)
    with pytest.raises(parallel.Unavailable):
        parallel.task("i", {"type": "object"})
    assert sent == []  # no key: no network
    monkeypatch.setenv("PARALLEL_API_KEY", "k")
    _fake(monkeypatch, 402)
    with pytest.raises(parallel.Unavailable, match="402"):
        parallel.image_search("o", ["q"])


def test_task_creates_a_run_then_reads_its_structured_result(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "k")
    basis = [{"field": "verdict", "citations": [{"url": "https://noaa.gov/m"}]}]
    result = {"output": {"type": "json", "content": {"verdict": "v"}, "basis": basis}}
    sent = _fake(monkeypatch, {"run_id": "r1"}, result)
    assert parallel.task("in", {"type": "object"}) == {"content": {"verdict": "v"}, "basis": basis}
    assert sent[0]["body"]["task_spec"]["output_schema"]["type"] == "json"
    assert sent[1]["method"] == "GET" and "/v1/tasks/runs/r1/result" in sent[1]["url"]


def test_findall_polls_until_the_run_stops_and_keeps_only_matches(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "k")
    monkeypatch.setattr(parallel.time, "sleep", lambda s: None)
    running = {"run": {"status": {"is_active": True}}, "candidates": []}
    done = {
        "run": {"status": {"is_active": False}},
        "candidates": [
            {"name": "NOAA", "match_status": "matched"},
            {"name": "X", "match_status": "unmatched"},
        ],
    }
    sent = _fake(monkeypatch, {"findall_id": "f1"}, running, done)
    assert [c["name"] for c in parallel.findall("o", "orgs")] == ["NOAA"]
    assert sent[0]["url"].endswith("/v1beta/findall/runs") and sent[0]["body"]["generator"]
    assert sent[2]["url"].endswith("/v1beta/findall/runs/f1/result")


def test_image_search_posts_to_the_images_endpoint(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "k")
    sent = _fake(monkeypatch, {"results": [{"image_url": "i"}]})
    assert parallel.image_search("o", ["q"]) == [{"image_url": "i"}]
    assert sent[0]["url"] == "https://api.parallel.ai/v1/images/search"
