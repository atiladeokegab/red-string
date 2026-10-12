"""The only sanctioned tuning run: practice cases, never the holdout.

    uv run scripts/tune.py cases/practice --out TUNING

It runs run_cases.py with --set practice, so every case id goes through tuning_cases() and no
holdout case can reach a prompt tweak, a few-shot pick or a threshold sweep. The report is the
out folder (one ANSWER.md per case); check it against the holdout with run_cases.py --compare.
"""

import argparse
import sys
from pathlib import Path

import run_cases  # scripts/ is on sys.path whenever a script in it runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", type=Path)
    parser.add_argument("--out", type=Path, default=Path("TUNING"))
    args = parser.parse_args(argv)
    return run_cases.main([str(args.cases), "--out", str(args.out), "--set", "practice"])


if __name__ == "__main__":
    sys.exit(main())
