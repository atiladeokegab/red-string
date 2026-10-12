"""The one tool door. Every tool the agent or an API caller uses goes through Gateway.call:
arguments are validated against the tool's type hints and the call is written to the event log.

A tool with an external effect (effect=True, the default) only runs when the gateway is live
(EFFECTS=live). Otherwise its function is never called: the gateway checks the arguments and
returns {"status": "SIMULATED", "payload": <the checked arguments, or simulate(**arguments)>}.
A read-only tool (effect=False) always runs and returns {"status": "OK", ...}, as does an effect
tool on a live gateway."""

import inspect
import threading
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from pydantic import validate_call

from starter.core.errors import CaseCancelled, NotFound
from starter.core.store import Store
from starter.core.tracing import tracer

# The case being run (the runner's case dict); the agent loop sets it, so a simulate= hook can
# check a call against the case without it being a tool argument.
current_case: ContextVar[dict | None] = ContextVar("current_case", default=None)


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

    def call(
        self, name: str, args: dict, case_id: str, cancel: threading.Event | None = None
    ) -> dict:
        """Validate, run (or simulate), audit. Bad arguments raise ValueError (HTTP 422). Once
        `cancel` is set, the call raises CaseCancelled: nothing runs and nothing is written."""
        if name not in self.tools:
            raise NotFound(f"no tool {name!r}")
        if cancel is not None and cancel.is_set():
            raise CaseCancelled("case cancelled")
        simulated = self.effects[name] and not self.live
        run = self.simulators[name] if simulated else self.tools[name]
        attributes = {"tool": name, "case_id": case_id, "simulated": simulated}
        attributes |= {f"arg.{k}": str(v) for k, v in args.items()}  # redacted on export
        with tracer.start_as_current_span("gateway.call", attributes=attributes):
            payload = run(**args)  # pydantic.ValidationError is a ValueError
        result = {"status": "SIMULATED" if simulated else "OK", "payload": payload}
        if cancel is not None and cancel.is_set():  # cancelled while the tool ran: no audit write
            raise CaseCancelled("case cancelled")
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
    """A gateway with every vertical's tools and get_skill registered."""
    from starter import verticals
    from starter.agent import skills

    gateway = Gateway(store, effects)
    for module in verticals.modules():
        if hasattr(module, "register_tools"):
            module.register_tools(gateway)
    skills.register_tools(gateway)  # get_skill: the system prompt's index names what it loads
    return gateway
