"""Run every case in a folder and write ANSWERS/<case>/{ANSWER.md, REASONING.md, trace.jsonl}.

    uv run scripts/run_cases.py cases/sample            # FakeProvider with no key, Claude with one
    uv run scripts/run_cases.py cases/sample --out /tmp/answers
    uv run scripts/run_cases.py cases/sample --set holdout --out ANSWERS-holdout
    uv run scripts/run_cases.py --compare ANSWERS-practice ANSWERS-holdout

A case is a folder holding index.md (and optionally history.md). ANSWER.md carries a
"Final state: <DONE|NEEDS_INFO|ESCALATED|ERROR>" line; every trace.jsonl line has "tool", "status"
and "error". A case that crashes, or runs past CASE_TIMEOUT_S, still gets both, with state
ERROR, and the run carries on; the exit code is 1 if any case crashed or timed out.
ANSWER.md also carries "Effects: <n> (<tool>: <count>, ...)": the effect calls this run's gateway
audit recorded for the case (crashed cases included), never the answer's own account, and an
"Effects mismatch:" line for each count the answer claims that the audit does not match.
<out>/README.md indexes the run: one row per case with its state, tool calls, tool errors, path
(live = Claude, fake = FakeProvider, none = never reached the model) and its answer's first line,
or for NEEDS_INFO the question it asked.

--set picks the cases: practice (through tuning_cases(), so never a holdout case), holdout, or all
(the default, for reports). The out folder's SET file records which one ran. Tune only through
scripts/tune.py, which always runs practice.

--compare PRACTICE HOLDOUT prints the final-state mix of a --set holdout run beside a --set
practice run and exits 2 when any state's share differs by more than 20 points: practice numbers
the holdout does not reproduce were tuned, not earned. It also exits 2 unless each folder is
labelled for its side and holds only that side's cases.
"""

import argparse
import json
import re
import sys
import threading
import time
import traceback
from collections import Counter
from pathlib import Path

from starter.agent.cases import load_case
from starter.agent.loop import AgentResult, run, step
from starter.core.gateway import build_gateway
from starter.core.store import open_store
from starter.eval.effects import claim_mismatches, count_effects, effects_line
from starter.eval.holdout import is_holdout, tuning_cases
from starter.runtime.config import Settings

FINAL_STATE = re.compile(r"^Final state: (\w+)$", re.MULTILINE)
STATES = ("DONE", "NEEDS_INFO", "ESCALATED", "ERROR")


def write_answer(out: Path, case_id: str, result: AgentResult, effects: str = "") -> None:
    """`effects` is the case's "Effects: ..." line(s), placed under the final state."""
    out.mkdir(parents=True, exist_ok=True)
    actions = [f"- `{a['tool']}` {a['status']}: {json.dumps(a['args'])}" for a in result.actions]
    head = f"# Answer: case {case_id}\n\nFinal state: {result.final_state}\n"
    head += f"{effects}\n" if effects else ""
    (out / "ANSWER.md").write_text(
        f"{head}\n{result.final_answer}\n\n## Actions\n\n" + ("\n".join(actions) or "None.") + "\n"
    )
    (out / "REASONING.md").write_text(f"# Reasoning: case {case_id}\n\n{result.reasoning}\n")
    (out / "trace.jsonl").write_text("".join(json.dumps(step) + "\n" for step in result.trace))
    (out / "spans.jsonl").write_text("".join(json.dumps(span) + "\n" for span in result.spans))


def write_index(out: Path, results: dict[str, AgentResult], which: str = "all") -> None:
    rows = [
        f"# Answers ({which} cases)\n",
        "| Case | Final state | Tool calls | Tool errors | Path | Answer |",
        "|---|---|---|---|---|---|",
    ]
    for case_id, result in sorted(results.items()):
        calls = [s for s in result.trace if s["type"] == "tool_call"]
        errors = sum(s["status"] == "ERROR" for s in calls)
        first = result.trace[0] if result.trace else {}
        provider = first.get("provider") if first.get("type") == "model_input" else None
        path = {"claude": "live", "fake": "fake", None: "none"}.get(provider, provider)
        lines = [line.strip() for line in result.final_answer.splitlines() if line.strip()]
        asked = [line for line in lines if line.endswith("?")]
        if result.final_state == "NEEDS_INFO" and asked:
            lines = asked
        answer = (lines or ["(empty)"])[0].replace("|", "\\|")
        rows.append(
            f"| {case_id} | {result.final_state} | {len(calls)} | {errors} | {path} | {answer} |"
        )
    (out / "README.md").write_text("\n".join(rows) + "\n")


class CaseTimeout(Exception):
    pass


def run_with_timeout(case: dict, gateway, settings: Settings) -> AgentResult:
    """Run one case on a daemon thread and give up on it after settings.case_timeout_s, so a hung
    model or tool call cannot block the cases after it."""
    # A timed-out case is told to stop (cancel): its thread runs no tool and writes nothing more;
    # a model call already in flight ends within its own timeout.
    box: dict = {}
    cancel = threading.Event()
    deadline = time.monotonic() + settings.case_timeout_s

    def target() -> None:
        try:
            box["result"] = run(case, gateway, settings, deadline=deadline, cancel=cancel)
        except Exception as exc:
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)  # daemon: a hung case can't block exit
    worker.start()
    worker.join(settings.case_timeout_s)
    if worker.is_alive():
        cancel.set()
        raise CaseTimeout(f"case timeout after {settings.case_timeout_s:g}s")
    if "error" in box:
        raise box["error"]
    return box["result"]


def select(folders: list[Path], which: str) -> list[Path]:
    """The case folders of one set: practice, holdout or all."""
    if which == "all":
        return folders
    if which == "holdout":
        return [f for f in folders if is_holdout(f.name)]
    practice = tuning_cases(f.name for f in folders if not is_holdout(f.name))
    return [f for f in folders if f.name in practice]


def compare_mix(practice: Path, holdout: Path, limit: float = 20) -> int:
    """Print each state's share of a holdout run beside a practice run; 2 if any share differs
    by more than `limit` points or the runs are not one labelled set each, else 0."""
    mix: dict[str, Counter] = {}
    for side, folder in (("holdout", holdout), ("practice", practice)):
        label = (folder / "SET").read_text().strip() if (folder / "SET").exists() else None
        if label != side:
            print(f"cannot compare: {folder} is not a --set {side} run (SET: {label})")
            return 2
        mix[side] = Counter()
        for answer in sorted(folder.glob("*/ANSWER.md")):
            case_id = answer.parent.name
            if is_holdout(case_id) != (side == "holdout"):
                print(f"cannot compare: case {case_id} in {folder} is not a {side} case")
                return 2
            match = FINAL_STATE.search(answer.read_text())
            mix[side][match.group(1) if match else "ERROR"] += 1
        if not mix[side]:
            print(f"cannot compare: no {side} cases in {folder}")
            return 2
    held, practised = mix["holdout"], mix["practice"]
    shifted = False
    print(f"{'state':<12}{'holdout':>9}{'practice':>10}{'diff':>7}")
    for state in STATES:
        a = 100 * held[state] / held.total()
        b = 100 * practised[state] / practised.total()
        shift = abs(a - b) > limit
        shifted |= shift
        print(f"{state:<12}{a:>8.0f}%{b:>9.0f}%{abs(a - b):>7.0f}" + ("  <- shift" * shift))
    print(f"{'cases':<12}{held.total():>9}{practised.total():>10}")
    return 2 if shifted else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", type=Path, nargs="?")
    parser.add_argument("--out", type=Path, default=Path("ANSWERS"))
    parser.add_argument("--set", choices=("practice", "holdout", "all"), default="all")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("PRACTICE", "HOLDOUT"))
    args = parser.parse_args(argv)
    if args.compare:
        return compare_mix(*args.compare)
    if args.cases is None:
        parser.error("give a cases folder, or --compare PRACTICE HOLDOUT")

    settings = Settings.from_env()
    gateway = build_gateway(open_store(settings.data_path), settings.mode_effects)
    folders = sorted(p for p in args.cases.iterdir() if (p / "index.md").exists())
    folders = select(folders, args.set)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "SET").write_text(f"{args.set}\n")
    failed = 0
    results: dict[str, AgentResult] = {}
    for folder in folders:
        seen = len(gateway.store.snapshot()["events"])  # the store outlives runs: count this one's
        try:
            case = load_case(folder)
            result = run_with_timeout(case, gateway, settings)
        except CaseTimeout as exc:
            failed += 1
            result = AgentResult(
                "No answer: the case did not finish in time.",
                "ERROR",
                f"Stopped by the runner: {exc}.",
                trace=[step("final", status="ERROR", error=str(exc), final_state="ERROR")],
            )
        except Exception as exc:
            failed += 1
            error = f"{type(exc).__name__}: {exc}"
            result = AgentResult(
                f"Run failed:\n\n```\n{traceback.format_exc()}```",
                "ERROR",
                "",
                trace=[step("final", status="ERROR", error=error, final_state="ERROR")],
            )
        counts = count_effects(
            gateway.store.snapshot()["events"][seen:], folder.name, gateway.effects
        )
        claims = claim_mismatches(result.final_answer, counts, gateway.effects)
        effects = "\n".join([effects_line(counts)] + [f"Effects mismatch: {c}" for c in claims])
        write_answer(args.out / folder.name, folder.name, result, effects)
        results[folder.name] = result
    write_index(args.out, results, args.set)
    print(f"{len(folders) - failed}/{len(folders)} cases answered in {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
