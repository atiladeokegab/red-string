"""POST /api/tts: 503 without a key, 400 for a stranger, and a cached line never calls OpenAI."""

import hashlib
from collections import defaultdict, deque

import httpx2
import pytest

from starter import tts


def test_missing_key_is_503(client, monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "CACHE", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert client.post("/api/tts", json={"who": "Editor", "text": "hi"}).status_code == 503


def test_bad_input_is_400(client):
    assert client.post("/api/tts", json={"who": "Mallory", "text": "hi"}).status_code == 400
    assert client.post("/api/tts", json={"who": "Editor", "text": ""}).status_code == 400
    assert client.post("/api/tts", json={"who": "Editor", "text": "x" * 301}).status_code == 400


def test_miss_calls_openai_once_then_cache_serves(client, monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "CACHE", tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json)
        return httpx2.Response(200, content=b"MP3", request=httpx2.Request("POST", url))

    monkeypatch.setattr(tts.httpx2, "post", fake_post)
    for _ in range(2):
        r = client.post("/api/tts", json={"who": "Sceptic", "text": "I doubt it."})
        assert r.status_code == 200 and r.content == b"MP3"
    assert len(calls) == 1 and calls[0]["voice"] == "sage"
    name = hashlib.sha256(b"Sceptic|I doubt it.").hexdigest() + ".mp3"
    assert (tmp_path / name).read_bytes() == b"MP3"
    monkeypatch.delenv("OPENAI_API_KEY")  # a cache hit needs no key either
    assert client.post("/api/tts", json={"who": "Sceptic", "text": "I doubt it."}).content == b"MP3"


def test_stt_missing_key_is_503(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = client.post("/api/stt", content=b"audio", headers={"content-type": "audio/webm"})
    assert r.status_code == 503


def test_stt_too_large_is_413(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = client.post("/api/stt", content=b"x" * (tts.STT_MAX + 1))
    assert r.status_code == 413


def test_stt_ok_forwards_audio_and_returns_text(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen = {}

    def fake_post(url, data, files, headers, timeout):
        seen.update(url=url, model=data["model"], file=files["file"])
        return httpx2.Response(
            200, json={"text": "who owns the pier"}, request=httpx2.Request("POST", url)
        )

    monkeypatch.setattr(tts.httpx2, "post", fake_post)
    headers = {"content-type": "audio/webm;codecs=opus"}
    r = client.post("/api/stt", content=b"OPUS", headers=headers)
    assert r.status_code == 200 and r.json() == {"text": "who owns the pier"}
    assert seen["url"].endswith("/v1/audio/transcriptions")
    assert seen["model"] == "gpt-4o-transcribe" and seen["file"] == ("premise.webm", b"OPUS")


@pytest.fixture
def fresh_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "CACHE", tmp_path)
    monkeypatch.setattr(tts, "_calls", deque())
    monkeypatch.setattr(tts, "_by_ip", defaultdict(deque))
    monkeypatch.setattr(tts, "_total", 0)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def fake_post(url, **kw):
        req = httpx2.Request("POST", url)
        if "speech" in url:
            return httpx2.Response(200, content=b"MP3", request=req)
        return httpx2.Response(200, json={"text": "hi"}, request=req)

    monkeypatch.setattr(tts.httpx2, "post", fake_post)


def _line(client, i, ip="1.1.1.1"):
    return client.post(
        "/api/tts", json={"who": "Editor", "text": f"line {i}"}, headers={"x-forwarded-for": ip}
    )


def test_per_ip_limit_is_429_but_cache_hits_stay_free(client, fresh_budget, monkeypatch):
    monkeypatch.setattr(tts, "PER_IP_MINUTE", 3)
    assert [_line(client, i).status_code for i in range(4)] == [200, 200, 200, 429]
    assert _line(client, 0).status_code == 200  # cached: no OpenAI call, no charge
    assert _line(client, 9, ip="2.2.2.2").status_code == 200  # another visitor still has budget


def test_per_minute_limit_covers_stt_too(client, fresh_budget, monkeypatch):
    monkeypatch.setattr(tts, "PER_MINUTE", 2)
    assert _line(client, 1, ip="a").status_code == 200
    assert client.post("/api/stt", content=b"OPUS").status_code == 200
    assert _line(client, 2, ip="b").status_code == 429
    assert client.post("/api/stt", content=b"OPUS").status_code == 429


def test_per_process_limit_never_resets(client, fresh_budget, monkeypatch):
    monkeypatch.setattr(tts, "PER_PROCESS", 2)
    _line(client, 1, ip="a"), _line(client, 2, ip="b")
    tts._calls.clear()  # a minute later, the per-minute window is empty
    assert _line(client, 3, ip="c").status_code == 429


def test_stt_cap_aborts_a_chunked_body_mid_stream(store, monkeypatch):
    """No Content-Length, 1 MB chunks: the route answers 413 after chunk three, not chunk ten."""
    import asyncio

    from starter.runtime.config import Settings
    from starter.runtime.factory import create_app

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    sent = []

    async def body():
        for i in range(10):
            sent.append(i)
            yield b"x" * (1024 * 1024)

    async def go():
        app = create_app(Settings(), store)
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://t") as http:
            return await http.post("/api/stt", content=body())

    assert asyncio.run(go()).status_code == 413
    assert len(sent) == 3
