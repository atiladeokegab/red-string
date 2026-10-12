"""Settings from the environment. Local mode runs offline with no keys; cloud mode refuses to
start without its secrets, so a missing key is a failed deploy, never a silent fake."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass(frozen=True)
class Settings:
    mode: str = "local"
    data_path: Path = Path("data/store.json")
    admin_password: str = "admin"
    anthropic_api_key: str | None = None
    model: str = DEFAULT_MODEL
    case_timeout_s: float = 120
    model_timeout_s: float = 60

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = dict(os.environ if env is None else env)
        mode = env.get("MODE", "local")
        if mode not in ("local", "cloud"):
            raise ValueError(f"MODE must be local or cloud, got {mode!r}")
        if mode == "cloud":
            missing = [k for k in ("ANTHROPIC_API_KEY", "ADMIN_PASSWORD") if not env.get(k)]
            if missing:
                raise RuntimeError(f"cloud mode refuses to start without {', '.join(missing)}")
        case_timeout_s = float(env.get("CASE_TIMEOUT_S", 120))
        model_timeout_s = float(env.get("MODEL_TIMEOUT_S", 60))
        if model_timeout_s >= case_timeout_s:
            raise ValueError("inner timeouts must be shorter than the case timeout")
        # ponytail: cloud keeps the JSON store in /tmp on one instance (deploy.sh pins
        # --max-instances 1), lost on restart; move to a GCS-backed store when demo state must
        # survive a redeploy.
        default_path = "/tmp/store.json" if mode == "cloud" else "data/store.json"
        return cls(
            mode=mode,
            data_path=Path(env.get("DATA_PATH", default_path)),
            admin_password=env.get("ADMIN_PASSWORD", "admin"),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
            model=env.get("MODEL", DEFAULT_MODEL),
            case_timeout_s=case_timeout_s,
            model_timeout_s=model_timeout_s,
        )

    def public(self) -> dict:
        """What is configured, safe to show anyone: never a secret."""
        return {
            "mode": self.mode,
            "model": self.model,
            "providers": {"anthropic": "configured" if self.anthropic_api_key else "fake"},
        }
