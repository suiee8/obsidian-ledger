"""Keep every source row of an import as Parquet, so the original data can be audited."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import duckdb

from obsidian_ledger.ingest.analysis import Source

BATCH_ROWS: Final = 50_000
INCOMING: Final = "incoming_raw"


def _identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def write_raw(source: Source, destination: Path) -> int:
    """Write every record below the header as text columns. Returns the rows written.

    Batches go in as Arrow-backed frames. DuckDB's executemany would run one statement
    per row.
    """
    import polars as pl

    headers = list(source.headers)
    width = len(headers)
    columns_sql = ", ".join(f"{_identifier(name)} VARCHAR" for name in headers)
    literal_path = str(destination).replace("'", "''")
    written = 0
    numbers: list[int] = []
    cells: list[list[str]] = [[] for _ in range(width)]

    connection = duckdb.connect()
    try:
        connection.execute(f"CREATE TABLE raw (source_row BIGINT, {columns_sql})")

        def flush() -> None:
            nonlocal written
            if not numbers:
                return
            frame = pl.DataFrame(
                [pl.Series("source_row", numbers, dtype=pl.Int64)]
                + [
                    pl.Series(headers[index], cells[index], dtype=pl.String)
                    for index in range(width)
                ]
            )
            connection.register(INCOMING, frame)
            try:
                connection.execute(f"INSERT INTO raw SELECT * FROM {INCOMING}")
            finally:
                connection.unregister(INCOMING)
            written += len(numbers)
            numbers.clear()
            for column in cells:
                column.clear()

        for number, row in source.iter_records():
            numbers.append(number)
            for index in range(width):
                cells[index].append(row[index] if index < len(row) else "")
            if len(numbers) >= BATCH_ROWS:
                flush()
        flush()
        connection.execute(f"COPY raw TO '{literal_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        connection.close()
    return written
