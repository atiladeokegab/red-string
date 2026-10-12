"""The one tool door. Every tool the agent or an API caller uses goes through Gateway.call:
arguments are validated against the tool's type hints and the call is written to the event log.

A tool with an external effect (effect=True, the default) only runs when the gateway is live
(EFFECTS=live). Otherwise its function is never called: the gateway checks the arguments and
returns {"status": "SIMULATED", "payload": <the checked arguments, or simulate(**arguments)>}.
A read-only tool (effect=False) always runs and returns {"status": "OK", ...}, as does an effect
tool on a live gateway."""

import inspect
from collections.abc import Callable
from typing import Any

from pydantic import validate_call

from starter.core.errors import NotFound
from starter.core.store import Store


class Gateway:
    def __init__(self, store: Store, effects: str = "simulate"):
        self.store = store
        self.live = effects == "live"
        self.tools: dict[str, Callable[..., Any]] = {}  # name -> argument-checking wrapper
        self.effects: dict[str, bool] = {}
        self.simulators: dict[str, Callable[..., Any]] = {}  # effect tools only

    def register(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        effect: bool = True,
        simulate: Callable[..., Any] | None = None,
    ):
        """Decorator. Type hints are the argument schema, the docstring is the description.
        simulate(**checked_arguments), if given, is the payload an effect tool returns when the
        gateway is not live; without it the payload is the checked arguments."""

        def add(fn: Callable[..., Any]) -> Callable[..., Any]:
            name = fn.__name__
            if name in self.tools:
                raise ValueError(f"tool {name!r} is already registered")
            self.tools[name] = validate_call(fn)
            self.effects[name] = effect
            if effect:
                check = validate_call(_arguments_of(fn))
                self.simulators[name] = lambda **args: (simulate or dict)(**check(**args))
            return fn

        return add(fn) if fn else add

    def call(self, name: str, args: dict, case_id: str) -> dict:
        """Validate, run (or simulate), audit. Bad arguments raise ValueError (HTTP 422)."""
        if name not in self.tools:
            raise NotFound(f"no tool {name!r}")
        simulated = self.effects[name] and not self.live
        run = self.simulators[name] if simulated else self.tools[name]
        payload = run(**args)  # pydantic.ValidationError is a ValueError
        result = {"status": "SIMULATED" if simulated else "OK", "payload": payload}
        self.store.publish(
            {"type": "tool_call", "case_id": case_id, "tool": name, "args": args, "result": result}
        )
        return result


def _arguments_of(fn: Callable[..., Any]) -> Callable[..., dict]:
    """A stand-in with fn's signature that returns its checked arguments and does nothing else."""

    def arguments(**kwargs) -> dict:
        return kwargs

    arguments.__signature__ = inspect.signature(fn).replace(return_annotation=dict)
    arguments.__annotations__ = {**inspect.get_annotations(fn), "return": dict}
    arguments.__name__, arguments.__qualname__ = fn.__name__, fn.__qualname__
    return arguments


def build_gateway(store: Store, effects: str = "simulate") -> Gateway:
    """A gateway with every vertical's tools registered."""
    from starter import verticals

    gateway = Gateway(store, effects)
    for module in verticals.modules():
        if hasattr(module, "register_tools"):
            module.register_tools(gateway)
    return gateway
