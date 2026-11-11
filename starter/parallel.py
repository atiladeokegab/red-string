"""Parallel web API: search (pull), respond (pull, researched answer), monitor (push).

Shapes from docs.parallel.ai, 2026-11-11. Run `uv run python -m starter.parallel` to check the key.
"""

import json
import os
import urllib.request

BASE = "https://api.parallel.ai/v1"


def _post(path: str, body: dict, timeout: float = 120) -> dict:
    key = os.environ["PARALLEL_API_KEY"]
    req = urllib.request.Request(
        f"{BASE}/{path}",
        data=json.dumps(body).encode(),
        # search/monitors document x-api-key, responses documents Bearer; send both
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "Authorization": f"Bearer {key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def search(objective: str, queries: list[str], max_results: int = 5) -> list[dict]:
    """-> [{url, title, publish_date, excerpts: [str]}]"""
    body = {
        "objective": objective,
        "search_queries": queries,
        "advanced_settings": {"max_results": max_results},
    }
    if os.environ.get("PARALLEL_API_KEY"):
        return _post("search", body)["results"]
    # shortcut: no key -> the free anonymous MCP endpoint (fast mode, lower rate limits)
    call = {"name": "web_search", "arguments": {"objective": objective, "search_queries": queries}}
    req = urllib.request.Request(
        "https://search.parallel.ai/mcp",
        data=json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": call}
        ).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        text = json.load(r)["result"]["content"][0]["text"]
    return json.loads(text)["results"][:max_results]


def respond(question: str, effort: str = "low") -> dict:
    """Researched answer -> {text, sources: [{url, title}]}. low ~3-10s, medium ~20s, high ~60s."""
    body = {"model": "parallel", "input": question, "reasoning": {"effort": effort}}
    parts = [
        c
        for i in _post("responses", body)["output"]
        if i["type"] == "message"
        for c in i["content"]
    ]
    seen = {a["url"]: a.get("title", "") for c in parts for a in c.get("annotations", [])}
    return {
        "text": "".join(c.get("text", "") for c in parts),
        "sources": [{"url": u, "title": t} for u, t in seen.items()],
    }


def monitor(query: str, webhook_url: str, frequency: str = "1h") -> dict:
    """Scheduled query; POSTs monitor.event.detected to webhook_url when the web changes."""
    body = {
        "type": "event_stream",
        "frequency": frequency,
        "processor": "lite",
        "settings": {"query": query},
        "webhook": {"url": webhook_url, "event_types": ["monitor.event.detected"]},
    }
    return _post("monitors", body)


if __name__ == "__main__":
    hits = search("What is Parallel Web Systems?", ["Parallel Web Systems"], 2)
    assert hits and hits[0]["url"], hits
    print("search ok:", hits[0]["url"])
    if not os.environ.get("PARALLEL_API_KEY"):
        raise SystemExit(
            "no PARALLEL_API_KEY: search ran on the free MCP; respond/monitor untested"
        )
    out = respond("What year was incident.io founded?")
    assert out["text"] and out["sources"], out
    print("respond ok:", out["text"][:120], "|", len(out["sources"]), "sources")
