"""Command-line entry point: ``python -m fuzz.run``.

Runs the seeded differential corpus and prints the report.  Deterministic:
the same ``--seed`` always produces the same corpus and the same numbers.

Usage::

    uv run --with email-validator python -m fuzz.run
    uv run --with email-validator python -m fuzz.run --seed 5322 --mutants 4000
    uv run --with email-validator python -m fuzz.run --replay 'a..b@example.com'

``--replay`` re-runs a single literal input against every reference, which is
how a reported failure is reproduced without regenerating the whole corpus.
"""

from __future__ import annotations

import argparse
import sys

from .corpus import handwritten
from .references import default_references
from .report import format_report, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fuzz.run", description=__doc__)
    parser.add_argument("--seed", type=int, default=5322)
    parser.add_argument("--mutants", type=int, default=4000)
    parser.add_argument("--max-examples", type=int, default=5)
    parser.add_argument(
        "--replay",
        metavar="TEXT",
        help="run one literal input against every reference and exit",
    )
    args = parser.parse_args(argv)

    if args.replay is not None:
        report = run(
            seed=args.seed,
            references=default_references(),
            cases=[("replay", args.replay)],
            max_examples=args.max_examples,
        )
        print(format_report(report))
        return 0

    report = run(
        seed=args.seed,
        n_mutants=args.mutants,
        max_examples=args.max_examples,
    )
    print(format_report(report))
    print(
        f"\nhand-written cases: {len(handwritten())}  "
        f"(re-run with --seed {args.seed})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
