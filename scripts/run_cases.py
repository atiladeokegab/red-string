"""Run every case in a folder and write ANSWERS/<case>/{ANSWER.md, REASONING.md, trace.jsonl}.

    uv run scripts/run_cases.py cases/sample            # FakeProvider with no key, Claude with one
    uv run scripts/run_cases.py cases/sample --out /tmp/answers

A case is a folder holding index.md (and optionally history.md). ANSWER.md carries a
"Final state: <DONE|NEEDS_INFO|ESCALATED|ERROR>" line; every trace.jsonl line has "tool", "status"
and "error". A case that crashes still gets both, with state ERROR, and the run carries on; the
exit code is 1 if any case crashed.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

from starter.agent.cases import load_case
from starter.agent.loop import AgentResult, run, step
from starter.core.gateway import build_gateway
from starter.core.store import Store
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", type=Path)
    parser.add_argument("--out", type=Path, default=Path("ANSWERS"))
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    gateway = build_gateway(Store(settings.data_path))
    folders = sorted(p for p in args.cases.iterdir() if (p / "index.md").exists())
    failed = 0
    for folder in folders:
        try:
            case = load_case(folder)
            write_answer(args.out / case["id"], case["id"], run(case, gateway, settings))
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
