# Red String

**Type a story. Watch fifty sources get pinned to the wall, and a red string snap between every
two that contradict each other.**

Red String is a citation crawler for journalists. You give it an investigative premise. It works out
who is in the story, reads the web's reporting on it, quotes what each source says about the
checkable facts (when did it happen, how much was it), and shows you where the sources disagree,
with the primary record (court, regulator, filing) marked in gold beside the press.

Built in two hours at the Agentic Web build night (Parallel x No Agenda, London, 11 Nov 2026).

## What you see

1. **One box, one button.** Type a premise, press Investigate.
2. **Who's who.** The people and organisations in the story appear first.
3. **The wall fills.** Each checkable question gets a panel. Every source is pinned under the
   answer it gives, with its exact quote and a link.
4. **Red string.** Where sources give different dates or amounts, a red string joins the
   disagreeing answers. Click it to read the quotes side by side.
5. **The verdict.** A short editor's note: what the sources agree on, where they differ, and what
   the primary record says.

Every quote on the wall is checked to be a real substring of the text the source returned. A claim
whose quote cannot be found is dropped, not shown. The tool reports what sources say; it makes no
claims of its own.

## How it uses Parallel

| Step | Parallel API | What it does |
|---|---|---|
| Identify the people and the checkable questions | Responses (`/v1/responses`) | One web-grounded answer, returned as JSON |
| Read the reporting | Search (`/v1/search`) | One search per question, run concurrently, about ten sources each |
| Quote what each source says | Responses | One call per question over that question's excerpts |
| Find the contradictions | none | Plain code: more than one distinct date or number for the same question |

The counter at the top of the page shows the real number of Parallel searches and sources read in
the run on screen.

## Run it

```bash
uv sync
echo "PARALLEL_API_KEY=your-key" > .env      # from platform.parallel.ai
set -a; . ./.env; set +a
uv run uvicorn starter.main:app --port 8000
# open http://localhost:8000/static/wall.html
```

**Replay** plays back a saved real run (`cases/runs/murdoch.json`) with no network, for when the
venue Wi-Fi does not cooperate. Add `?replay` to the URL to start it on load.

`make check` runs the lint and the offline tests.

## Pre-existing work

The FastAPI app factory, store, agent loop and deploy scripts under `starter/` come from a starter
kit written before the event. Written at the event: `starter/parallel.py`,
`starter/investigate.py`, `starter/web/static/wall.html`, their tests, and this README.

## Known limits

- "Primary record" is a domain rule (courts, government, regulators, filings, archives), not a
  judgement about the document.
- It reads the excerpts Parallel's search returns, not every full page.
- Parallel's Monitor API (re-check the story on a schedule and push new contradictions) is wired in
  the client but not used by the page yet.
