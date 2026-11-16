"""Part R: the market-selection collector, run over this experiment's cases.

    uv run python -m evals.market_issuer_share_v1.collect --src <checkout>/src --arm old|new \\
        --cache <file outside the repo> --out <dir> --accessed YYYY-MM-DD --env <.env> [--only V06,U03]

The collector is ``evals/market_selection_v1/collect.py``, unchanged: one
recorder answers both arms, so the two registries differ only where the code
does. Only the list of cases is this experiment's. Run it as a module from
the root of this branch, whichever arm's ``--src`` it is given.
"""

from __future__ import annotations

from pathlib import Path

from evals.market_selection_v1 import collect

CASES = Path(__file__).with_name("cases.json")


def main(argv: list[str] | None = None) -> int:
    collect.CASES = CASES
    return collect.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
