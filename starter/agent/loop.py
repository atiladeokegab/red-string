"""The product agent: one case in, an AgentResult out. Claude drives the gateway's tools through
the SDK tool runner when ANTHROPIC_API_KEY is set; otherwise FakeProvider runs the same tools
deterministically, so everything works offline.

The trace is what reviewers read: every step is a dict with at least "tool", "status" (SIMULATED,
OK or ERROR) and "error" (None or the message). trace[0] is exactly what the model was given; one
"tool_call" step per tool call, failed ones included; the last step carries the final state."""

import json
import re
from dataclasses import dataclass, field

from anthropic import beta_tool

from starter.core.gateway import Gateway
from starter.runtime.config import Settings

SYSTEM = (
    "You handle one case for the operations team. Read it, act through the tools, and finish "
    "with a short final answer saying what you did and why. Every tool call is simulated and "
    "logged; never claim an action you did not take through a tool. End the final answer with "
    "exactly one line: STATE: DONE (handled), STATE: NEEDS_INFO (you need more from someone "
    "before acting) or STATE: ESCALATED (a person must decide)."
)
STATE_LINE = re.compile(r"^[ \t]*STATE:[ \t]*(DONE|NEEDS_INFO|ESCALATED)[ \t]*$", re.MULTILINE)


@dataclass
class AgentResult:
    final_answer: str
    final_state: str  # DONE | NEEDS_INFO | ESCALATED | ERROR
    reasoning: str
    actions: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)


def step(kind: str, tool: str | None = None, status: str = "OK", error: str | None = None, **rest):
    return {"type": kind, "tool": tool, "status": status, "error": error, **rest}


def parse_state(answer: str) -> tuple[str, str]:
    """(state, answer without the STATE line). No STATE line means ERROR: nothing is assumed."""
    states = STATE_LINE.findall(answer)
    if not states:
        return "ERROR", answer.strip()
    return states[-1], STATE_LINE.sub("", answer).strip()


def build_messages(case: dict) -> list[dict]:
    return [{"role": "user", "content": f"Case {case['id']}\n\n{case['body']}"}]


def gateway_tools(gateway: Gateway, case_id: str, actions: list[dict], trace: list[dict]) -> list:
    """Each gateway tool as an SDK tool bound to this case. Arguments are checked by the gateway
    alone, so a bad call is traced as ERROR before the runner hands the error back to Claude."""

    def bind(name: str, fn):
        spec = beta_tool(fn)  # schema and description from the tool's type hints and docstring

        def call(**args):
            try:
                result = gateway.call(name, args, case_id)
            except Exception as exc:
                trace.append(step("tool_call", name, "ERROR", str(exc), args=args))
                raise
            trace.append(
                step("tool_call", name, result["status"], args=args, payload=result["payload"])
            )
            actions.append({"tool": name, "args": args, **result})
            return json.dumps(result)

        return beta_tool(
            call, name=name, description=spec.description, input_schema=spec.input_schema
        )

    return [bind(name, fn) for name, fn in gateway.tools.items()]


class FakeProvider:
    """Offline stand-in: calls send_message once, then answers. Named in every output."""

    name = "fake"

    def run(self, system: str, messages: list[dict], tools: list, trace: list[dict]):
        # ponytail: always the example vertical's send_message; teach it your tools if the
        # offline demo needs a different first action.
        tool = next(t for t in tools if t.name == "send_message")
        tool.call({"to": "case-owner", "body": "We have your case and are working on it."})
        answer = (
            "FakeProvider (no ANTHROPIC_API_KEY): acknowledged the case with one message.\n"
            "STATE: DONE"
        )
        return answer, "FakeProvider is deterministic: one acknowledgement, then stop."


class ClaudeProvider:
    name = "claude"

    def __init__(self, settings: Settings):
        import anthropic

        self.model = settings.model
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=settings.model_timeout_s
        )

    def run(self, system: str, messages: list[dict], tools: list, trace: list[dict]):
        runner = self.client.beta.messages.tool_runner(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=messages,
            tools=tools,
            max_iterations=20,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": "high"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # a safety decline is retried on a fallback model, same call
        )
        notes, last = [], None
        for message in runner:
            last = message
            content = [block.to_dict() for block in message.content]
            trace.append(step("model_output", stop_reason=message.stop_reason, content=content))
            notes += [b.thinking for b in message.content if b.type == "thinking" and b.thinking]
        reasoning = "\n\n".join(notes)
        if last is None:
            return "No response from the model.", reasoning
        if last.stop_reason == "refusal":
            category = last.stop_details.category if last.stop_details else None
            return f"The model declined this case (category: {category}).", reasoning
        return "".join(b.text for b in last.content if b.type == "text"), reasoning


def run(case: dict, gateway: Gateway, settings: Settings, provider=None) -> AgentResult:
    """Run one case. case = {"id": str, "body": str}, already stripped of its outcome."""
    if provider is None:
        provider = ClaudeProvider(settings) if settings.anthropic_api_key else FakeProvider()
    messages = build_messages(case)
    actions: list[dict] = []
    trace: list[dict] = []
    tools = gateway_tools(gateway, case["id"], actions, trace)
    trace.append(
        step(
            "model_input",
            provider=provider.name,
            model=settings.model,
            system=SYSTEM,
            messages=messages,
            tools=[t.to_dict() for t in tools],
        )
    )
    try:
        answer, reasoning = provider.run(SYSTEM, messages, tools, trace)
        state, answer = parse_state(answer)
        error = None if state != "ERROR" else f"no STATE line in the final answer: {answer[:200]}"
    except Exception as exc:  # the case still gets an answer and a trace saying what broke
        state, answer, reasoning, error = "ERROR", "", "", f"{type(exc).__name__}: {exc}"
    trace.append(
        step("final", status="ERROR" if state == "ERROR" else "OK", error=error, final_state=state)
    )
    return AgentResult(answer, state, reasoning, actions, trace)
