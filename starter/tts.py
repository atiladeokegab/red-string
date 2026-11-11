"""Crew voices: POST /api/tts speaks one crew line with OpenAI TTS, cached by sha256(who|text).
The key comes only from OPENAI_API_KEY and never leaves the server; without it the route answers
503 and voice.js falls back to the browser's speechSynthesis."""

import hashlib
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import httpx2
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

CACHE = Path(
    os.environ.get("TTS_CACHE", "/tmp/red-string-tts")
)  # /tmp: writable for the non-root container user
URL = "https://api.openai.com/v1/audio/speech"
VOICES = {  # who: (voice, instructions)
    "Editor": ("marin", "Calm, warm, authoritative newsroom editor pulling the story together."),
    "Identifier": ("cedar", "Brisk, eager field researcher naming who is in the story."),
    "Archivist": ("coral", "Precise, bookish archivist, quietly pleased with a good record."),
    "Timekeeper": ("ash", "Clipped, exact timekeeper, ticking off dates like a metronome."),
    "Sceptic": ("sage", "Dry, suspicious, deadpan newsroom sceptic who doubts everything."),
}

router = APIRouter()  # public like investigate.router: the demo front end has no login


# Cost guard for both paid routes (cache hits are free): OpenAI calls per minute, process, IP.
PER_MINUTE, PER_PROCESS, PER_IP_MINUTE = 40, 600, 30
_calls: deque[float] = deque()
_by_ip: defaultdict[str, deque[float]] = defaultdict(deque)
_total = 0
_lock = threading.Lock()


def _ip(request: Request) -> str:
    # shortcut: X-Forwarded-For is spoofable; the global caps are the real ceiling. Fine for a demo.
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


def spend(request: Request) -> None:
    """Count one OpenAI call or raise 429. Call it after validation, just before the request."""
    global _total
    now, ip = time.monotonic(), _ip(request)
    with _lock:
        for q in (_calls, _by_ip[ip]):
            while q and now - q[0] > 60:
                q.popleft()
        if _total >= PER_PROCESS or len(_calls) >= PER_MINUTE or len(_by_ip[ip]) >= PER_IP_MINUTE:
            raise HTTPException(429, "voice budget spent; the browser voice takes over")
        _total += 1
        _calls.append(now)
        _by_ip[ip].append(now)


class Line(BaseModel):
    text: str
    who: str


@router.post("/api/tts")
def tts(line: Line, request: Request) -> FileResponse:
    if not 1 <= len(line.text) <= 300 or line.who not in VOICES:
        raise HTTPException(400, "text must be 1-300 chars and who a crew name")
    path = CACHE / (hashlib.sha256(f"{line.who}|{line.text}".encode()).hexdigest() + ".mp3")
    if not path.exists():
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise HTTPException(503, "OPENAI_API_KEY is not set")
        spend(request)
        voice, instructions = VOICES[line.who]
        body = {
            "model": "gpt-4o-mini-tts",
            "voice": voice,
            "input": line.text,
            "instructions": instructions,
            "response_format": "mp3",
        }
        try:
            r = httpx2.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=15)
            r.raise_for_status()
        except httpx2.HTTPError as e:  # the message names the URL and status, never the key
            raise HTTPException(502, f"OpenAI TTS failed: {type(e).__name__}") from None
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(
            f".{os.urandom(6).hex()}.part"
        )  # per-request temp: concurrent misses for one line cannot collide
        tmp.write_bytes(r.content)
        tmp.replace(path)  # atomic: a half-written mp3 is never served
    return FileResponse(path, media_type="audio/mpeg")


STT_URL = "https://api.openai.com/v1/audio/transcriptions"
STT_MAX = 2 * 1024 * 1024
AUDIO = {
    "webm",
    "ogg",
    "mp4",
    "mpeg",
    "wav",
    "m4a",
}  # MediaRecorder types; OpenAI reads the extension


@router.post("/api/stt")
async def stt(request: Request) -> dict:
    """The mic: raw audio body (MediaRecorder blob) in, {"text": ...} out."""
    audio = await request.body()
    if len(audio) > STT_MAX:
        raise HTTPException(413, "audio over 2 MB")
    if not audio:
        raise HTTPException(400, "no audio")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, "OPENAI_API_KEY is not set")
    spend(request)
    ext = request.headers.get("content-type", "").split(";")[0].split("/")[-1]
    name = f"premise.{ext if ext in AUDIO else 'webm'}"
    try:
        r = await run_in_threadpool(
            httpx2.post,
            STT_URL,
            data={"model": "gpt-4o-transcribe"},
            files={"file": (name, audio)},
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
        r.raise_for_status()
    except httpx2.HTTPError as e:  # never echo the key
        raise HTTPException(502, f"OpenAI STT failed: {type(e).__name__}") from None
    return {"text": r.json().get("text", "")}
