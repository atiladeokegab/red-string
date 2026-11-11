# /// script
# requires-python = ">=3.11"
# dependencies = ["diagrams"]
# ///
"""C4 diagrams for Red String, drawn from the real code, levels 1-3.

    uv run docs/architecture/c4.py           # writes c4_context.png ... c4_component.png here
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
)

# diagrams.c4 wraps text at 40 characters but draws 2.6in boxes, which fit about 34:
# lines of 35-40 characters were cut off, silently. 3.3in fits the full wrap width.
Container, Database, Person, System = (
    partial(f, width="3.3") for f in (Container, Database, Person, System)
)

# Level 3 boxes. Python-icon nodes are 1.4in wide with the label hung below, so a long signature
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

SYSTEM = "Red String"
OUT = Path(__file__).parent
GRAPH = {"splines": "spline", "nodesep": "0.8", "ranksep": "1.1"}
RULE = "──"  # box-drawing rule under a function name


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
        journalist = Person("Journalist", "Types an investigative premise, reads the wall")
        system = System(
            SYSTEM,
            "Turns a premise into sources, quoted claims and the dates and numbers "
            "where sources contradict each other",
        )
        parallel = System(
            "Parallel Web Systems API",
            "api.parallel.ai: /v1/search and /v1/responses",
            external=True,
        )
        web = System(
            "The web's sources",
            "News reports, court and regulator filings, official statements",
            external=True,
        )
        journalist >> Relationship("premise in, live wall out (HTTPS, SSE)") >> system
        system >> Relationship("searches, structured answers (HTTPS, JSON)") >> parallel
        parallel >> Relationship("searches and reads") >> web


def container():
    """Level 2: the separately running pieces, and how they talk."""
    with draw("container", "Containers"):
        journalist = Person("Journalist", "")
        api = System("Parallel Web Systems API", "api.parallel.ai/v1", external=True)
        with SystemBoundary(SYSTEM):
            wall = Container(
                "Wall page",
                "static wall.html: EventSource + SVG",
                "Pins entities, questions, sources and claims; draws the red strings",
            )
            routes = Container(
                "SSE routes",
                "FastAPI, runtime/factory.py",
                "GET /api/investigate?premise= and /api/investigate/replay?name=",
            )
            engine = Container(
                "Engine",
                "starter/investigate.py",
                "investigate(premise): a generator of event dicts",
            )
            client = Container(
                "Parallel client", "starter/parallel.py", "search() and respond() over urllib"
            )
            runs = Database("Saved runs", "cases/runs/*.json", "A run's event list, for replay")
        journalist >> Relationship("types a premise, or clicks Replay") >> wall
        wall >> Relationship("EventSource GET") >> routes
        routes >> Relationship("live: iterates events") >> engine
        routes >> Relationship("replay: reads, no network") >> runs
        engine >> Relationship("search(), respond()") >> client
        engine >> Relationship("CLI run writes events") >> runs
        client >> Relationship("POST /search, /responses") >> api


def component():
    """Level 3: inside the engine. The steps of investigate(), in order, and what each emits."""
    with draw("component", "Components of the engine (starter/investigate.py)"):
        routes = Container("SSE routes", "FastAPI", "Each yielded dict becomes one data: line")
        client = Container("Parallel client", "starter/parallel.py", "search() and respond()")
        # a short cluster label: the edge from the routes passes beside it, not through it
        with Cluster("investigate(premise)"):
            plan = Code(
                f"1. Plan: _plan()\n{RULE}\nup to 8 entities and 8 questions,\n"
                "each asking one date or one number\nemits: entity, question"
            )
            search = Code(
                f"2. Search: _search()\n{RULE}\ntwo searches per question (reporting,\n"
                "primary records), questions concurrent\nemits: source"
            )
            claims = Code(
                f"3. Claims: _claims()\n{RULE}\na claim is dropped unless its quote is\n"
                "a verbatim substring of the excerpt\nemits: claim"
            )
            conflicts = Code(
                f"4. Conflicts: find_conflict()\n{RULE}\nplain code: more than one distinct\n"
                "date or number for a question;\nprimary-record domains marked\nemits: conflict"
            )
            verdict = Code(
                f"5. Verdict: _verdict()\n{RULE}\ntwo sentences from the tally, plus a\n"
                "primary-record sentence built in code\nemits: verdict"
            )
        # one two-way edge: the route calls the generator and every step's events come back up it
        (
            routes
            >> Edge(
                label="premise in; events out, with stats\nafter each step, error when one fails",
                reverse=True,
            )
            >> plan
        )
        plan >> Edge(label="questions") >> search
        search >> Edge(label="excerpts per question") >> claims
        claims >> Edge(label="claims per question") >> conflicts
        conflicts >> Edge(label="conflicts") >> verdict
        plan >> Edge(label="respond(schema)") >> client
        search >> Edge(label="search() x2") >> client
        claims >> Edge(label="respond(schema)") >> client
        verdict >> Edge(label="respond()") >> client


LEVELS = {n: globals()[n] for n in ("context", "container", "component")}

if __name__ == "__main__":
    if not shutil.which("dot"):
        sys.exit(
            "c4: Graphviz is not installed (no `dot` on PATH). Run: sudo apt install -y graphviz"
        )
    for name in sys.argv[1:] or LEVELS:
        LEVELS[name]()
        print(OUT / f"c4_{name}.png")
