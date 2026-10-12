"""make smoke is offline and deterministic even when the environment carries a real key."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_smoke_cases_use_the_fake_provider_with_a_key_in_the_env(tmp_path):
    env = {
        **os.environ,
        "ANTHROPIC_API_KEY": "sk-ant-a-real-looking-key",
        "MODE": "cloud",  # a copied .env may say cloud; the smoke still runs locally
        "EFFECTS": "live",
        "SMOKE_OUT": str(tmp_path),
    }
    done = subprocess.run(
        ["make", "-s", "smoke-cases"], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stdout + done.stderr
    traces = sorted((tmp_path / "ANSWERS").glob("*/trace.jsonl"))
    assert len(traces) == 5
    for trace in traces:
        first = json.loads(trace.read_text().splitlines()[0])
        assert first["provider"] == "fake"
    actions = (tmp_path / "ANSWERS" / "001" / "ANSWER.md").read_text()
    assert "SIMULATED" in actions  # EFFECTS forced back to simulate
    assert (tmp_path / "store.json").exists()  # the smoke never touches data/store.json
