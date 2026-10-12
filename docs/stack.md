# Stack

Decided rows change only by review. To use a Proposed row or add a dependency, add or edit a row
with its reason and ask in review: dependency files are gated.

| Layer | Choice | Status | Why |
|---|---|---|---|
| Language and packaging | Python 3.12, uv, `uv.lock` | Decided | One toolchain; the lockfile makes the image reproducible |
| Web | FastAPI + uvicorn, one image serving pages and API | Decided | One deploy, one factory, typed request bodies |
| Pages | Jinja2 templates + `static/tokens.css` | Decided | Designer mockups drop in as templates; one brand slot (`--accent`) |
| State | JSON file store, flock + atomic replace | Decided | Zero setup, offline, enough for a demo |
| Agent | Anthropic SDK tool runner, `claude-opus-5-5` from `MODEL` | Decided | The loop is the SDK's; we own only the tools |
| Offline provider | `FakeProvider` | Decided | `make dev`, `make check` and the runner work with no keys |
| Tests and lint | pytest, ruff | Decided | `make check` is the gate |
| Deploy | Docker + Cloud Run via `gcloud run deploy --source .` | Decided | Build, push and deploy in one command; image labelled with the commit |
| Secrets | Google Secret Manager | Decided | Keys never in the repo or the image |
| Durable state | `GcsStore`: the same `Store` contract on one GCS object, compare-and-swap on its generation; picked by `DATA_PATH=gs://...` | Decided | Survives a redeploy; up to 3 instances share it; a few writes a second |
| Tool protocol | MCP server at `/mcp` (official `mcp` SDK, Streamable HTTP, stateless) in front of the gateway | Decided | One door for every outside agent; same image; every call audited |
| Telemetry | OpenTelemetry SDK, spans as redacted JSON lines (stdout and `ANSWERS/<n>/spans.jsonl`) | Decided | Evidence beside every answer; no collector to run |
| Grading | LLM judge over `ANSWERS/` | Proposed | When outcomes can't be checked by string |
| Infra as code | Terraform | Proposed | Only when a project outlives an event |
