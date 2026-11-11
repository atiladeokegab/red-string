"""POST /api/tts: 503 without a key, 400 for a stranger, and a cached line never calls OpenAI."""

import hashlib

import httpx2

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
