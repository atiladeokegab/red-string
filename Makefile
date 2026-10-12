.PHONY: dev check deploy

dev:
	uv run uvicorn starter.main:app --reload

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q

deploy:
	scripts/deploy.sh
