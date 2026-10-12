import pytest
from fastapi.testclient import TestClient

from starter.core.store import Store
from starter.runtime.config import Settings
from starter.runtime.deps import session_token
from starter.runtime.factory import create_app


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    """Tests never see the developer's keys: every test runs offline, in local mode."""
    for name in ("ANTHROPIC_API_KEY", "ADMIN_PASSWORD", "MODE", "DATA_PATH", "MODEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "store.json")


@pytest.fixture
def client(store):
    return TestClient(create_app(Settings(), store))


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {session_token(Settings().admin_password)}"}
