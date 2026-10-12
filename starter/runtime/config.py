"""Settings from the environment. Local mode runs offline with no keys; cloud mode refuses to
start without its secrets, so a missing key is a failed deploy, never a silent fake."""

import os
from dataclasses import dataclass

DEFAULT_MODEL = "claude-opus-5-5"
MODEL_MAX_RETRIES = 1  # the SDK retries a timed-out call; each try gets the model timeout
EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class Settings:
    mode: str = "local"
    data_path: str = "data/store.json"  # a file path, or gs://bucket/object for GcsStore
    admin_password: str = "admin"
    anthropic_api_key: str | None = None
    model: str = DEFAULT_MODEL
    mode_effects: str = "simulate"  # "live" lets effect tools act; anything else simulates
    case_timeout_s: float = 120
    model_timeout_s: float = 50
    max_iterations: int = 8  # model calls per case
    effort: str = "medium"

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
        effects = env.get("EFFECTS", "simulate")
        if effects not in ("simulate", "live"):
            raise ValueError(f"EFFECTS must be simulate or live, got {effects!r}")
        effort = env.get("EFFORT", "medium")
        if effort not in EFFORTS:
            raise ValueError(f"EFFORT must be one of {', '.join(EFFORTS)}, got {effort!r}")
        case_timeout_s = float(env.get("CASE_TIMEOUT_S", 120))
        model_timeout_s = float(env.get("MODEL_TIMEOUT_S", 50))
        if (1 + MODEL_MAX_RETRIES) * model_timeout_s >= case_timeout_s:
            raise ValueError("inner timeouts must be shorter than the case timeout")
        # Cloud without DATA_PATH keeps the JSON store in /tmp, lost on restart; deploy.sh sets
        # DATA_PATH=gs://... so state survives a redeploy and several instances share it.
        default_path = "/tmp/store.json" if mode == "cloud" else "data/store.json"
        return cls(
            mode=mode,
            data_path=env.get("DATA_PATH", default_path),
            admin_password=env.get("ADMIN_PASSWORD", "admin"),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
            model=env.get("MODEL", DEFAULT_MODEL),
            mode_effects=effects,
            case_timeout_s=case_timeout_s,
            model_timeout_s=model_timeout_s,
            max_iterations=int(env.get("MAX_ITERATIONS", 8)),
            effort=effort,
        )

    def public(self) -> dict:
        """What is configured, safe to show anyone: never a secret."""
        return {
            "mode": self.mode,
            "model": self.model,
            "effects": self.mode_effects,
            "providers": {"anthropic": "configured" if self.anthropic_api_key else "fake"},
        }
