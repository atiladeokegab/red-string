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
from diagrams.c4 import Container, Database, Person, Relationship, System, SystemBoundary

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
        system = System(SYSTEM, "One FastAPI image: pages, API, tool gateway, agent loop")
        claude = System("Claude API", "Model behind the agent loop (opus-5-5)", external=True)
        gcp = System(
            "Google Cloud",
            "Cloud Build, Cloud Run and Secret Manager: build, serve, keys",
            external=True,
        )
        team >> Relationship("HTTPS, make dev, run_cases.py") >> system
        team >> Relationship("make deploy") >> gcp
        system >> Relationship("tool runner, only with a key") >> claude
        gcp >> Relationship("runs the image, with secrets") >> system


def container():
    """Level 2: the separately running or deployed pieces, and how they talk."""
    with draw("container", "Containers"):
        team = Person("Teammate or judge", "")
        claude = System("Claude API", "Model timeout 50s, one retry", external=True)
        cloud_run = System("Cloud Run", "Builds the Dockerfile, serves one instance", external=True)
        with SystemBoundary(SYSTEM):
            web = Container("Web app", "FastAPI + uvicorn", "Pages, /api, /health; one image")
            runner = Container(
                "Case runner", "scripts/run_cases.py", "cases/<n> to ANSWERS/<n>, case timeout"
            )
            deploy = Container(
                "Deploy script", "scripts/deploy.sh + Dockerfile", "Clean tree, commit label"
            )
            store = Database("Store", "JSON file + flock", "Items, runs, the event log")
        team >> Relationship("HTTPS") >> web
        team >> Relationship("uv run") >> runner
        team >> Relationship("make deploy") >> deploy
        deploy >> Relationship("gcloud run deploy --source") >> cloud_run
        deploy >> Relationship("probes /health") >> web
        cloud_run >> Relationship("runs, with secrets") >> web
        web >> Relationship("snapshot / mutate") >> store
        runner >> Relationship("audit events") >> store
        web >> Relationship("messages + tools") >> claude
        runner >> Relationship("messages + tools") >> claude


def component():
    """Level 3: inside the web app. Runs start at the agent routes, not at a vertical."""
    with draw("component", "Components of the web app"):
        claude = System("Claude API", "", external=True)
        with SystemBoundary("Web app"):
            factory = Container(
                "Factory", "runtime/factory.py", "/health, /healthz, login, errors, logs"
            )
            config = Container("Settings", "runtime/config.py", "Env, secrets check, timeouts")
            verticals = Container("Verticals", "verticals/*.py", "router, seed, register_tools")
            routes = Container("Agent routes", "agent/routes.py", "/api/tools, /api/runs")
            loop = Container("Agent loop", "agent/loop.py", "Claude or FakeProvider")
            gateway = Container("Gateway", "core/gateway.py", "Validate, audit, SIMULATED")
            store = Container("Store", "core/store.py", "snapshot, mutate, publish")
            pages = Container("Pages", "web/pages.py", "Runs page, tokens.css")
        factory >> Relationship("reads") >> config
        factory >> Relationship("mounts") >> verticals
        factory >> Relationship("mounts") >> routes
        factory >> Relationship("mounts") >> pages
        routes >> Relationship("run(case)") >> loop
        routes >> Relationship("call(name, args)") >> gateway
        routes >> Relationship("mutate: runs") >> store
        loop >> Relationship("tools") >> gateway
        loop >> Relationship("tool runner, timeout") >> claude
        verticals >> Relationship("register_tools") >> gateway
        gateway >> Relationship("publish") >> store
        pages >> Relationship("snapshot") >> store


def code():
    """Level 4: the classes and signatures the rest of the code depends on."""
    with draw("code", "Code"):
        with Cluster("starter/core"):
            store = Code(
                f"Store\n{RULE}\n+ snapshot() → dict\n+ mutate(fn) → T\n+ publish(event) → dict"
            )
            gateway = Code(
                f"Gateway\n{RULE}\n+ register(fn, effect=True)\n+ call(name, args,\n"
                "    case_id) → dict"
            )
        with Cluster("starter/agent"):
            loop = Code("run(case, gateway, settings,\n    provider=None) → AgentResult")
            result = Code(
                f"AgentResult\n{RULE}\n+ final_answer: str\n+ final_state: str\n"
                "+ reasoning: str\n+ actions: list[dict]\n+ trace: list[dict]"
            )
            claude = Code(
                f"ClaudeProvider\n{RULE}\n+ client: Anthropic(timeout,\n    max_retries=1)\n"
                "+ run(system, messages,\n    tools, trace)"
            )
            cases = Code("load_case(folder) → dict\nstrip_outcome(text) → str")
        with Cluster("starter/runtime"):
            settings = Code(
                f"Settings\n{RULE}\n+ case_timeout_s = 120\n+ model_timeout_s = 50\n"
                "+ from_env(env)\n+ public() → dict"
            )
            factory = Code("create_app(settings=None,\n    store=None) → FastAPI")
        with Cluster("scripts/run_cases.py"):
            runner = Code("run_with_timeout(case,\n    gateway, settings)\n    → AgentResult")
        factory >> Edge(label="builds") >> gateway
        factory >> Edge(label="reads") >> settings
        runner >> Edge(label="daemon thread,\ncase timeout") >> loop
        cases >> Edge(label="case dict") >> loop
        loop >> Edge(label="returns") >> result
        loop >> Edge(label="calls") >> gateway
        loop >> Edge(label="provider.run") >> claude
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
