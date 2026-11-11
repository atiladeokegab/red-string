"""Parallel web API: search, extract, respond, task, findall, image search (pull), monitor (push).

Shapes from docs.parallel.ai, 2026-11-11. Run `uv run python -m starter.parallel` to check the key.
Search and extract fall back to the keyless MCP (search.parallel.ai/mcp: web_search, web_fetch)
when there is no key or the keyed API refuses; the other endpoints raise Unavailable.
"""

import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://api.parallel.ai"
MCP = "https://search.parallel.ai/mcp"


class Unavailable(Exception):
    """No key, or the keyed API refused: 402 (credits), 429 or 5xx. Callers degrade."""


def _post(path: str, body: dict | None, timeout: float = 120) -> dict:
    """POST body to BASE/path, or GET when body is None."""
    key = os.environ.get("PARALLEL_API_KEY")
    if not key:
        raise Unavailable(f"{path}: no PARALLEL_API_KEY")
    req = urllib.request.Request(
        f"{BASE}/{path}",
        data=None if body is None else json.dumps(body).encode(),
        # search/monitors document x-api-key, responses documents Bearer; send both
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        if exc.code in (402, 429) or exc.code >= 500:
            raise Unavailable(f"{path}: HTTP {exc.code}") from exc
        raise


def _mcp(tool: str, args: dict, timeout: float = 60) -> dict:
    """One tools/call on the free anonymous MCP (fast mode, lower rate limits)."""
    req = urllib.request.Request(
        MCP,
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            }
        ).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(json.load(r)["result"]["content"][0]["text"])


def search(objective: str, queries: list[str], max_results: int = 5) -> list[dict]:
    """-> [{url, title, publish_date, excerpts: [str]}]"""
    body = {
        "objective": objective,
        "search_queries": queries,
        "advanced_settings": {"max_results": max_results},
    }
    try:
        return _post("v1/search", body)["results"]
    except Unavailable:
        args = {"objective": objective, "search_queries": queries}
        return _mcp("web_search", args)["results"][:max_results]


def extract(urls: list[str], objective: str, timeout: float = 60) -> list[dict]:
    """Fetch the live pages now -> [{url, title, publish_date, excerpts, full_content}]."""
    # max_age 600 s is the floor: anything older is re-fetched from the site, not the index
    settings = {"full_content": True, "fetch_policy": {"max_age_seconds": 600}}
    body = {"urls": urls, "objective": objective, "advanced_settings": settings}
    try:
        return _post("v1/extract", body, timeout)["results"]
    except Unavailable:
        args = {
            "urls": urls,
            "objective": objective,
            "full_content": True,
            "allow_live_fetch": True,
        }
        return _mcp("web_fetch", args, timeout)["results"]


def task(input: str, schema: dict, processor: str = "lite", timeout: float = 120) -> dict:
    """Task API run -> {content: <schema-shaped dict>, basis: [{field, citations: [{url,...}]}]}."""
    spec = {"output_schema": {"type": "json", "json_schema": schema}}
    run = _post("v1/tasks/runs", {"input": input, "processor": processor, "task_spec": spec}, 30)
    wait = int(timeout)
    out = _post(f"v1/tasks/runs/{run['run_id']}/result?timeout={wait}", None, wait + 10)["output"]
    return {"content": out["content"], "basis": out.get("basis") or []}


def findall(objective: str, entity_type: str, timeout: float = 90) -> list[dict]:
    """FindAll preview run -> matched candidates [{name, url, description}]."""
    body = {
        "objective": objective,
        "entity_type": entity_type,
        "match_conditions": [{"name": "involved", "description": objective}],
        "generator": "preview",
        "match_limit": 5,
    }
    run_id = _post("v1beta/findall/runs", body, 30)["findall_id"]
    deadline = time.monotonic() + timeout
    while True:
        out = _post(f"v1beta/findall/runs/{run_id}/result", None, 30)
        if not out["run"]["status"]["is_active"] or time.monotonic() > deadline:
            break
        time.sleep(3)
    return [c for c in out.get("candidates", []) if c.get("match_status") == "matched"]


def image_search(objective: str, queries: list[str], timeout: float = 30) -> list[dict]:
    """-> [{title, image_url, source_page_url, width, height}]"""
    return _post("v1/images/search", {"objective": objective, "search_queries": queries}, timeout)[
        "results"
    ]


def respond(question: str, effort: str = "low", schema: dict | None = None) -> dict:
    """Researched answer -> {text, sources: [{url, title}]}. low ~3-10s, medium ~20s, high ~60s.

    schema: a JSON Schema (object root) the text must satisfy (Structured Outputs)."""
    body = {"model": "parallel", "input": question, "reasoning": {"effort": effort}}
    if schema:
        fmt = {"type": "json_schema", "name": "answer", "strict": True, "schema": schema}
        body["text"] = {"format": fmt}
    parts = [
        c
        for i in _post("v1/responses", body)["output"]
        if i["type"] == "message"
        for c in i["content"]
    ]
    seen = {a["url"]: a.get("title", "") for c in parts for a in c.get("annotations", [])}
    return {
        "text": "".join(c.get("text", "") for c in parts),
        "sources": [{"url": u, "title": t} for u, t in seen.items()],
    }


def monitor(query: str, webhook_url: str, frequency: str = "1h", timeout: float = 30) -> dict:
    """Scheduled query; POSTs monitor.event.detected to webhook_url when the web changes."""
    body = {
        "type": "event_stream",
        "frequency": frequency,
        "processor": "lite",
        "settings": {"query": query},
        "webhook": {"url": webhook_url, "event_types": ["monitor.event.detected"]},
    }
    return _post("v1/monitors", body, timeout)


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
