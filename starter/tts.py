"""Crew voices: POST /api/tts speaks one crew line with OpenAI TTS, cached by sha256(who|text).
The key comes only from OPENAI_API_KEY and never leaves the server; without it the route answers
503 and voice.js falls back to the browser's speechSynthesis."""

import hashlib
import os
from pathlib import Path

import httpx2
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

CACHE = Path(".tts-cache")
URL = "https://api.openai.com/v1/audio/speech"
VOICES = {  # who: (voice, instructions)
    "Editor": ("marin", "Calm, warm, authoritative newsroom editor pulling the story together."),
    "Identifier": ("cedar", "Brisk, eager field researcher naming who is in the story."),
    "Archivist": ("coral", "Precise, bookish archivist, quietly pleased with a good record."),
    "Timekeeper": ("ash", "Clipped, exact timekeeper, ticking off dates like a metronome."),
    "Sceptic": ("sage", "Dry, suspicious, deadpan newsroom sceptic who doubts everything."),
}

router = APIRouter()  # public like investigate.router: the demo front end has no login


class Line(BaseModel):
    text: str
    who: str


@router.post("/api/tts")
def tts(line: Line) -> FileResponse:
    if not 1 <= len(line.text) <= 300 or line.who not in VOICES:
        raise HTTPException(400, "text must be 1-300 chars and who a crew name")
    path = CACHE / (hashlib.sha256(f"{line.who}|{line.text}".encode()).hexdigest() + ".mp3")
    if not path.exists():
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise HTTPException(503, "OPENAI_API_KEY is not set")
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
        CACHE.mkdir(exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(path)  # atomic: a half-written mp3 is never served
    return FileResponse(path, media_type="audio/mpeg")
