# /// script
# requires-python = ">=3.11"
# dependencies = ["diagrams"]
# ///
"""C4 diagrams for the hackathon starter, drawn from the real code, levels 1-4.

    uv run docs/architecture/c4.py           # writes c4_context.png ... c4_code.png here
    uv run docs/architecture/c4.py context   # just one level

Redraw after any change to a box or an arrow, and look at every PNG before committing it.
"""

import shutil
import sys
from functools import partial
from pathlib import Path

from diagrams import Cluster, Diagram, Edge, Node
from diagrams.c4 import (
    Container,
    Database,
    Person,
    Relationship,
    System,
    SystemBoundary,
    _format_edge_label,  # the same small font as every edge label
)

# diagrams.c4 wraps text at 40 characters but draws 2.6in boxes, which fit about 34:
# lines of 35-40 characters were cut off, silently. 3.3in fits the full wrap width.
Container, Database, Person, System = (
    partial(f, width="3.3") for f in (Container, Database, Person, System)
)

# Level 4 boxes. Python-icon nodes are 1.4in wide with the label hung below, so a long signature
# spilled past the node and arrows ran through the words; a box sized to its text keeps them clear.
Code = partial(
    Node,
    shape="box",
    style="rounded,filled",
    fillcolor="white",
    color="#7B8894",
    fixedsize="false",
    labelloc="c",
    margin="0.3,0.15",
)

SYSTEM = "Hackathon starter"
OUT = Path(__file__).parent
GRAPH = {"splines": "spline", "nodesep": "0.8", "ranksep": "1.1"}
RULE = "──"  # box-drawing rule under a class name


def draw(level, title, **graph):
    return Diagram(
        f"{SYSTEM} - {title}",
        filename=str(OUT / f"c4_{level}"),
        outformat="png",
        show=False,
        direction="TB",
        graph_attr=GRAPH | graph,
    )


def context():
    """Level 1: who uses it and what it depends on. The system is ONE box."""
    with draw("context", "System Context"):
        team = Person("Teammate or judge", "Opens the demo, runs cases, reads the answers")
        agent = System(
            "Coding agent", "Claude Code or any MCP client, with a session token", external=True
        )
        system = System(SYSTEM, "One FastAPI image: pages, API, MCP door, gateway, agent loop")
        claude = System("Claude API", "Model behind the agent loop (opus-5-5)", external=True)
        gcp = System(
            "Google Cloud",
            "Cloud Run, Cloud Build, Secret Manager, the state bucket, logs",
            external=True,
        )
        team >> Relationship("HTTPS, make dev, make smoke, run_cases.py") >> system
        agent >> Relationship("MCP over HTTPS") >> system
        team >> Relationship("make deploy") >> gcp
        system >> Relationship("tool runner, only with a key") >> claude
        gcp >> Relationship("runs the image, with secrets") >> system
        system >> Relationship("state object, spans in logs") >> gcp


def container():
    """Level 2: the separately running or deployed pieces, and how they talk."""
    with draw("container", "Containers"):
        team = Person("Teammate or judge", "")
        agent = System("Coding agent", "MCP client", external=True)
        claude = System("Claude API", "Per-call timeout capped by the case budget", external=True)
        cloud_run = System("Cloud Run", "Builds the Dockerfile, up to 3 instances", external=True)
        with SystemBoundary(SYSTEM):
            web = Container("Web app", "FastAPI + uvicorn", "Pages, /api, /mcp, /health; spans")
            runner = Container(
                "Case runner",
                "scripts/run_cases.py",
                "cases/<n> to ANSWERS/<n> with spans; budget, cancel",
            )
            sweep = Container(
                "Eval scripts", "scripts/trace_sweep.py, tune.py", "Read ANSWERS: tool errors, mix"
            )
            deploy = Container(
                "Deploy script", "scripts/deploy.sh + Dockerfile", "Clean tree, bucket, instances"
            )
            store = Database(
                "Store", "JSON file or GCS object", "Local file; GCS with compare-and-swap"
            )
        team >> Relationship("HTTPS") >> web
        agent >> Relationship("MCP, bearer token") >> web
        team >> Relationship("uv run, make smoke") >> runner
        team >> Relationship("reviewer runs") >> sweep
        team >> Relationship("make deploy") >> deploy
        # xlabel: a flat edge's label sits in its curve; placed after layout, it stays clear
        deploy >> Relationship(xlabel=_format_edge_label("gcloud run deploy --source")) >> cloud_run
        deploy >> Relationship("probes /health") >> web
        cloud_run >> Relationship("runs, with secrets") >> web
        web >> Relationship("snapshot / mutate") >> store
        runner >> Relationship("audit events") >> store
        sweep >> Relationship("reads ANSWERS") >> runner
        web >> Relationship("messages + tools") >> claude
        runner >> Relationship("messages + tools") >> claude


def component():
    """Level 3: inside the web app. Every tool call, from any door, goes through the gateway."""
    with draw("component", "Components of the web app"):
        claude = System("Claude API", "", external=True)
        with SystemBoundary("Web app"):
            factory = Container(
                "Factory", "runtime/factory.py", "/health, login, errors, a span per request"
            )
            config = Container("Settings", "runtime/config.py", "EFFECTS, budget, effort, store")
            mcp = Container("MCP door", "runtime/mcp_door.py", "/mcp, session tokens")
            verticals = Container("Verticals", "verticals/*.py", "router, seed, register_tools")
            routes = Container("Agent routes", "agent/routes.py", "/api/tools, /api/runs")
            loop = Container("Agent loop", "agent/loop.py", "Claude or FakeProvider, budget")
            skills = Container("Skills", "agent/skills/", "Preamble, get_skill")
            gateway = Container("Gateway", "core/gateway.py", "Validate, simulate, cancel, audit")
            tracing = Container("Tracing", "core/tracing.py", "Redacted spans as JSON lines")
            store = Container("Store", "core/store.py", "Store or GcsStore")
            pages = Container("Pages", "web/pages.py", "Runs page, tokens.css")
        factory >> Relationship("reads") >> config
        factory >> Relationship("mounts") >> verticals
        factory >> Relationship("mounts") >> routes
        factory >> Relationship("mounts") >> mcp
        factory >> Relationship("mounts") >> pages
        mcp >> Relationship("call(name, args)") >> gateway
        routes >> Relationship("run(case)") >> loop
        routes >> Relationship("call(name, args)") >> gateway
        routes >> Relationship("mutate: runs") >> store
        loop >> Relationship("system_prompt") >> skills
        loop >> Relationship("tools, cancel") >> gateway
        loop >> Relationship("tool runner, timeout") >> claude
        loop >> Relationship("case span") >> tracing
        skills >> Relationship("register_tools") >> gateway
        verticals >> Relationship("register_tools") >> gateway
        gateway >> Relationship("gateway.call span") >> tracing
        gateway >> Relationship("publish") >> store
        pages >> Relationship("snapshot") >> store


def code():
    """Level 4: the classes and signatures the rest of the code depends on."""
    with draw("code", "Code"):
        with Cluster("starter/core"):
            store = Code(
                f"Store / GcsStore\n{RULE}\n+ snapshot() → dict\n+ mutate(fn) → T\n"
                "+ publish(event) → dict\nopen_store(path) → Store"
            )
            gateway = Code(
                f"Gateway(store, effects)\n{RULE}\n"
                "+ register(fn, effect=True,\n    simulate=None)\n"
                "+ call(name, args, case_id,\n    cancel=None) → dict"
            )
            tracing = Code("collect(name) → (trace_id, spans)\nredact(value)\ntracer, EXPORTER")
        with Cluster("starter/agent"):
            loop = Code(
                "run(case, gateway, settings,\n    provider=None, deadline=None,\n"
                "    cancel=None) → AgentResult\nsystem_prompt() → str"
            )
            result = Code(
                f"AgentResult\n{RULE}\n+ final_answer, final_state\n+ reasoning: str\n"
                "+ actions, trace: list[dict]\n+ trace_id: str\n+ spans: list[dict]"
            )
            claude = Code(
                f"ClaudeProvider\n{RULE}\n+ client: Anthropic(timeout,\n    max_retries=1)\n"
                "+ run(system, messages, tools,\n    trace, seconds_left)"
            )
            skills = Code("skills.preamble() → str\nget_skill(name) → str")
        with Cluster("starter/runtime"):
            settings = Code(
                f"Settings\n{RULE}\n+ mode_effects = simulate\n+ case_timeout_s = 120\n"
                "+ max_iterations = 8\n+ effort = medium\n+ data_path: str"
            )
            factory = Code("create_app(settings=None,\n    store=None) → FastAPI")
            mcp = Code("build_mcp(gateway) → MCPServer\nissue_token(password) → str")
        with Cluster("scripts/run_cases.py"):
            runner = Code("run_with_timeout(case,\n    gateway, settings)\n    → AgentResult")
        factory >> Edge(label="builds") >> gateway
        factory >> Edge(label="reads") >> settings
        factory >> Edge(label="mounts /mcp") >> mcp
        mcp >> Edge(label="calls") >> gateway
        runner >> Edge(label="deadline,\ncancel") >> loop
        loop >> Edge(label="returns") >> result
        loop >> Edge(label="calls") >> gateway
        loop >> Edge(label="provider.run") >> claude
        loop >> Edge(label="prompt") >> skills
        loop >> Edge(label="case span") >> tracing
        gateway >> Edge(label="publish") >> store


LEVELS = {n: globals()[n] for n in ("context", "container", "component", "code")}

if __name__ == "__main__":
    if not shutil.which("dot"):
        sys.exit(
            "c4: Graphviz is not installed (no `dot` on PATH). Run: sudo apt install -y graphviz"
        )
    for name in sys.argv[1:] or LEVELS:
        LEVELS[name]()
        print(OUT / f"c4_{name}.png")
