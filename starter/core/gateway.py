"""The one tool door. Every tool the agent or an API caller uses goes through Gateway.call:
arguments are validated against the tool's type hints, the call is written to the event log,
and a tool with an external effect returns {"status": "SIMULATED", ...} because nothing real
leaves the building. A read-only tool (effect=False) returns {"status": "OK", ...}."""

from collections.abc import Callable
from typing import Any

from pydantic import validate_call

from starter.core.errors import NotFound
from starter.core.store import Store


class Gateway:
    def __init__(self, store: Store):
        self.store = store
        self.tools: dict[str, Callable[..., Any]] = {}  # name -> argument-checking wrapper
        self.effects: dict[str, bool] = {}

    def register(self, fn: Callable[..., Any] | None = None, *, effect: bool = True):
        """Decorator. Type hints are the argument schema, the docstring is the description."""

        def add(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[fn.__name__] = validate_call(fn)
            self.effects[fn.__name__] = effect
            return fn

        return add(fn) if fn else add

    def call(self, name: str, args: dict, case_id: str) -> dict:
        """Validate, run, audit. Bad arguments raise ValueError (HTTP 422); works for any case."""
        if name not in self.tools:
            raise NotFound(f"no tool {name!r}")
        payload = self.tools[name](**args)  # pydantic.ValidationError is a ValueError
        result = {"status": "SIMULATED" if self.effects[name] else "OK", "payload": payload}
        self.store.publish(
            {"type": "tool_call", "case_id": case_id, "tool": name, "args": args, "result": result}
        )
        return result


def build_gateway(store: Store) -> Gateway:
    """A gateway with every vertical's tools registered."""
    from starter import verticals

    gateway = Gateway(store)
    for module in verticals.modules():
        if hasattr(module, "register_tools"):
            module.register_tools(gateway)
    return gateway
