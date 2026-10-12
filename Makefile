.PHONY: dev check smoke smoke-cases eval deploy mcp

MCP_URL ?= http://127.0.0.1:8000/mcp

dev:
	uv run uvicorn starter.main:app --reload

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q

# The merge gate: offline and deterministic even when .env holds a real key. Never calls a model.
smoke: check smoke-cases

smoke-cases:
	out="$${SMOKE_OUT:-$$(mktemp -d)}" && \
	ANTHROPIC_API_KEY= MODE=local EFFECTS=simulate DATA_PATH="$$out/store.json" \
	uv run scripts/run_cases.py cases/sample --out "$$out/ANSWERS"

# The real model on the sample cases, for the reviewer on agent/core PRs. Costs money; never a gate.
eval:
	@test -n "$$ANTHROPIC_API_KEY" || { echo "make eval needs ANTHROPIC_API_KEY"; exit 1; }
	-EFFECTS=simulate uv run scripts/run_cases.py cases/sample --out ANSWERS

deploy:
	scripts/deploy.sh

mcp:
	uv run python -m starter.runtime.mcp_door $(MCP_URL)
