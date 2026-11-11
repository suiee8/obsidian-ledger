"""Write a deterministic synthetic journal.

Examples:
  python benchmarks/generate_trades.py --rows 1000 --out samples/synthetic_preview.csv
  python benchmarks/generate_trades.py --rows 100000 --out samples/synthetic_100k.csv
  python benchmarks/generate_trades.py --rows 1000000 --out benchmarks/out/synthetic_1m.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ledger_samples import generate_rows, write_csv, write_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a deterministic USD trade journal.")
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    if args.rows < 1:
        print("--rows must be at least 1", file=sys.stderr)
        return 2
    rows = generate_rows(args.rows, seed=args.seed)
    write_csv(rows, args.out)
    manifest = args.manifest or args.out.with_suffix(".manifest.json")
    write_manifest(rows, args.out, manifest, seed=args.seed)
    print(f"wrote {args.rows} trades to {args.out}")
    print(f"wrote manifest to {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
