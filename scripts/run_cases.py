"""Run every case in a folder and write ANSWERS/<case>/{ANSWER.md, REASONING.md, trace.jsonl}.

    uv run scripts/run_cases.py cases/sample            # FakeProvider with no key, Claude with one
    uv run scripts/run_cases.py cases/sample --out /tmp/answers
    uv run scripts/run_cases.py cases/sample --set holdout --out ANSWERS-holdout

A case is a folder holding index.md (and optionally history.md). ANSWER.md carries a
"Final state: <DONE|NEEDS_INFO|ESCALATED|ERROR>" line; every trace.jsonl line has "tool", "status"
and "error". A case that crashes, or runs past CASE_TIMEOUT_S, still gets both, with state
ERROR, and the run carries on; the exit code is 1 if any case crashed or timed out.

--set picks the cases: practice (through tuning_cases(), so never a holdout case), holdout, or all
(the default, for reports). The out folder's SET file records which one ran. Tune only through
scripts/tune.py, which always runs practice.
"""

import argparse
import json
import sys
import threading
import traceback
from pathlib import Path

from starter.agent.cases import load_case
from starter.agent.loop import AgentResult, run, step
from starter.core.gateway import build_gateway
from starter.core.store import Store
from starter.eval.holdout import is_holdout, tuning_cases
from starter.runtime.config import Settings


def write_answer(out: Path, case_id: str, result: AgentResult) -> None:
    out.mkdir(parents=True, exist_ok=True)
    actions = [f"- `{a['tool']}` {a['status']}: {json.dumps(a['args'])}" for a in result.actions]
    (out / "ANSWER.md").write_text(
        f"# Answer: case {case_id}\n\nFinal state: {result.final_state}\n\n"
        f"{result.final_answer}\n\n## Actions\n\n" + ("\n".join(actions) or "None.") + "\n"
    )
    (out / "REASONING.md").write_text(f"# Reasoning: case {case_id}\n\n{result.reasoning}\n")
    (out / "trace.jsonl").write_text("".join(json.dumps(step) + "\n" for step in result.trace))


class CaseTimeout(Exception):
    pass


def run_with_timeout(case: dict, gateway, settings: Settings) -> AgentResult:
    """Run one case on a daemon thread and give up on it after settings.case_timeout_s, so a hung
    model or tool call cannot block the cases after it."""
    # ponytail: a timed-out case is abandoned, not killed: its thread may still finish and log
    # tool calls; make the loop async and cancellable if abandoned work ever matters.
    box: dict = {}

    def target() -> None:
        try:
            box["result"] = run(case, gateway, settings)
        except Exception as exc:
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)  # daemon: a hung case can't block exit
    worker.start()
    worker.join(settings.case_timeout_s)
    if worker.is_alive():
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", type=Path)
    parser.add_argument("--out", type=Path, default=Path("ANSWERS"))
    parser.add_argument("--set", choices=("practice", "holdout", "all"), default="all")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    gateway = build_gateway(Store(settings.data_path))
    folders = sorted(p for p in args.cases.iterdir() if (p / "index.md").exists())
    folders = select(folders, args.set)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "SET").write_text(f"{args.set}\n")
    failed = 0
    for folder in folders:
        try:
            case = load_case(folder)
            result = run_with_timeout(case, gateway, settings)
            write_answer(args.out / case["id"], case["id"], result)
        except CaseTimeout as exc:
            failed += 1
            timed_out = AgentResult(
                "No answer: the case did not finish in time.",
                "ERROR",
                f"Stopped by the runner: {exc}.",
                trace=[step("final", status="ERROR", error=str(exc), final_state="ERROR")],
            )
            write_answer(args.out / folder.name, folder.name, timed_out)
        except Exception as exc:
            failed += 1
            error = f"{type(exc).__name__}: {exc}"
            crashed = AgentResult(
                f"Run failed:\n\n```\n{traceback.format_exc()}```",
                "ERROR",
                "",
                trace=[step("final", status="ERROR", error=error, final_state="ERROR")],
            )
            write_answer(args.out / folder.name, folder.name, crashed)
    print(f"{len(folders) - failed}/{len(folders)} cases answered in {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
