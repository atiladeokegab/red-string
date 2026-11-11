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
    return _post("search", body)["results"]


def respond(question: str, effort: str = "low") -> dict:
    """Researched answer in ["output_text"]. effort: low ~5-10s, medium ~15-20s, high ~30-60s."""
    return _post(
        "responses", {"model": "parallel", "input": question, "reasoning": {"effort": effort}}
    )


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
    out = respond("What year was incident.io founded?")
    print("respond ok:", str(out.get("output_text") or out)[:200])
