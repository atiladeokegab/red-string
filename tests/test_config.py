import json

import pytest

from starter.runtime.config import Settings


def test_local_defaults_need_no_keys():
    s = Settings.from_env({})
    assert (s.mode, s.model, s.anthropic_api_key) == ("local", "claude-opus-5-5", None)
    assert s.public()["providers"] == {"anthropic": "fake"}


def test_cloud_refuses_missing_secrets():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY, ADMIN_PASSWORD"):
        Settings.from_env({"MODE": "cloud"})


def test_cloud_with_secrets_starts_and_public_hides_them():
    env = {"MODE": "cloud", "ANTHROPIC_API_KEY": "sk-secret", "ADMIN_PASSWORD": "pw"}
    s = Settings.from_env(env)
    assert s.mode == "cloud" and str(s.data_path) == "/tmp/store.json"
    shown = json.dumps(s.public())
    assert "sk-secret" not in shown and "pw" not in shown
    assert s.public()["providers"] == {"anthropic": "configured"}


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        Settings.from_env({"MODE": "prod"})
