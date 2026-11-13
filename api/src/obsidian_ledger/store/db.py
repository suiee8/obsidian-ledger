"""Local DuckDB store: trades, import records, mapping templates, and derived views."""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import duckdb
import polars as pl

from obsidian_ledger.ingest.frames import TRADE_DTYPES, frame_from_trades
from obsidian_ledger.ingest.trade import Trade

DB_FILE: Final = "ledger.duckdb"
LOSS_STREAK_FLAG: Final = 3

SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS trades (
    trade_key VARCHAR PRIMARY KEY,
    import_id VARCHAR NOT NULL,
    trade_id VARCHAR NOT NULL,
    account VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    asset_class VARCHAR,
    side VARCHAR NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP NOT NULL,
    source_timezone VARCHAR,
    qty DOUBLE NOT NULL,
    multiplier DOUBLE NOT NULL,
    entry_price DOUBLE,
    exit_price DOUBLE,
    fees DOUBLE NOT NULL,
    commission DOUBLE NOT NULL,
    swap DOUBLE NOT NULL,
    gross_pnl DOUBLE,
    net_pnl DOUBLE,
    currency VARCHAR NOT NULL,
    net_pnl_base DOUBLE,
    base_currency VARCHAR NOT NULL,
    stop_loss DOUBLE,
    take_profit DOUBLE,
    planned_risk DOUBLE,
    r_multiple DOUBLE,
    mae DOUBLE,
    mfe DOUBLE,
    setup VARCHAR,
    timeframe VARCHAR,
    session VARCHAR NOT NULL,
    tags VARCHAR,
    notes VARCHAR NOT NULL,
    emotion VARCHAR,
    plan_followed BOOLEAN,
    holding_seconds DOUBLE NOT NULL,
    weekday INTEGER NOT NULL,
    hour_utc INTEGER NOT NULL,
    source_row INTEGER NOT NULL,
    screenshot_path VARCHAR,
    confidence VARCHAR
    ,time_precision VARCHAR NOT NULL DEFAULT 'second'
    ,entry_notional DOUBLE
    ,exit_notional DOUBLE
    ,leverage DOUBLE
    ,order_type VARCHAR
    ,status VARCHAR
    ,action VARCHAR
);
CREATE TABLE IF NOT EXISTS activity_events (
    event_key VARCHAR PRIMARY KEY,
    import_id VARCHAR NOT NULL,
    account VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    direction VARCHAR,
    action VARCHAR,
    quantity DOUBLE,
    notional DOUBLE,
    event_time TIMESTAMP,
    time_precision VARCHAR NOT NULL,
    leverage DOUBLE,
    order_type VARCHAR,
    status VARCHAR,
    source_row INTEGER NOT NULL,
    duplicate BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS settings (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL);
CREATE TABLE IF NOT EXISTS imports (
    import_id VARCHAR PRIMARY KEY,
    filename VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    record_json VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_views (
    name VARCHAR PRIMARY KEY,
    config_json VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS coach_reports (
    report_id VARCHAR PRIMARY KEY,
    dataset_version VARCHAR NOT NULL,
    filter_key VARCHAR NOT NULL,
    params_key VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    report_json VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS mapping_templates (
    fingerprint VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    mapping_json VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
"""

# Derived fields are computed over the whole table, so they stay correct when a second file
# is merged. Equity and drawdown use base-currency P&L. Trades without an FX rate count as zero.
TRADE_VIEW: Final = f"""
CREATE OR REPLACE VIEW trade_view AS
WITH params AS (
    SELECT
        COALESCE(
            (SELECT CAST(value AS DOUBLE) FROM settings WHERE key = 'starting_equity'),
            0.0
        ) AS start_equity,
        (SELECT COUNT(*) FROM settings WHERE key = 'starting_equity') > 0 AS has_equity
),
ordered AS (
    SELECT t.*,
        CASE WHEN t.net_pnl IS NULL THEN NULL ELSE COALESCE(t.net_pnl_base, 0.0) END AS pnl_base
    FROM trades t
),
running AS (
    SELECT
        o.*,
        LAG(o.qty) OVER (ORDER BY o.entry_time, o.trade_key) AS prev_qty,
        SUM(o.pnl_base) OVER w AS cum_pnl,
        SUM(CASE WHEN o.pnl_base > 0 THEN 1 ELSE 0 END) OVER w AS win_group
    FROM ordered o
    WINDOW w AS (ORDER BY o.exit_time, o.trade_key ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),
equity AS (
    SELECT r.*, p.start_equity, p.has_equity, p.start_equity + r.cum_pnl AS equity
    FROM running r CROSS JOIN params p
),
peaks AS (
    SELECT
        e.*,
        GREATEST(
            e.start_equity,
            MAX(e.equity) OVER (
                ORDER BY e.exit_time, e.trade_key
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )
        ) AS peak_equity
    FROM equity e
),
streaks AS (
    SELECT
        k.*,
        SUM(CASE WHEN k.pnl_base <= 0 THEN 1 ELSE 0 END) OVER (
            PARTITION BY k.win_group
            ORDER BY k.exit_time, k.trade_key
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS loss_streak
    FROM peaks k
)
SELECT
    trade_key, trade_id, import_id, account, symbol, asset_class, side,
    entry_time, exit_time, source_timezone, qty, multiplier, entry_price, exit_price,
    fees, commission, swap, gross_pnl, net_pnl, currency, net_pnl_base, base_currency,
    stop_loss, take_profit, planned_risk, r_multiple, mae, mfe, setup, timeframe,
    session, tags, notes, emotion, plan_followed, holding_seconds, weekday, hour_utc,
    source_row, time_precision, entry_notional, exit_notional, leverage, order_type, status, action,
    screenshot_path,
    confidence,
    pnl_base,
    cum_pnl AS cumulative_pnl_base,
    equity,
    peak_equity,
    equity - peak_equity AS drawdown,
    CASE
        WHEN has_equity AND (equity - pnl_base) <> 0 THEN planned_risk / (equity - pnl_base)
    END AS risk_pct,
    loss_streak,
    loss_streak >= {LOSS_STREAK_FLAG} AS loss_streak_flag,
    CASE WHEN prev_qty IS NULL OR prev_qty = 0 THEN NULL ELSE qty / prev_qty - 1 END AS size_change
FROM streaks
"""

INCOMING: Final = "incoming_trades"

# Databases created before these columns existed get them appended, which keeps the
# positional insert in the same order as a fresh table.
MIGRATIONS: Final = """
ALTER TABLE trades ADD COLUMN IF NOT EXISTS screenshot_path VARCHAR;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS confidence VARCHAR;
ALTER TABLE trades ALTER COLUMN fees DROP NOT NULL;
ALTER TABLE trades ALTER COLUMN commission DROP NOT NULL;
ALTER TABLE trades ALTER COLUMN swap DROP NOT NULL;
ALTER TABLE trades ALTER COLUMN gross_pnl DROP NOT NULL;
ALTER TABLE trades ALTER COLUMN net_pnl DROP NOT NULL;
ALTER TABLE trades ALTER COLUMN holding_seconds DROP NOT NULL;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS time_precision VARCHAR DEFAULT 'second';
ALTER TABLE trades ADD COLUMN IF NOT EXISTS entry_notional DOUBLE;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS exit_notional DOUBLE;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS leverage DOUBLE;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS order_type VARCHAR;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS status VARCHAR;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS action VARCHAR;
"""


def _first(rows: list[tuple[Any, ...]]) -> tuple[Any, ...] | None:
    """First row of a fully fetched result. Fully fetching keeps the connection usable."""
    return rows[0] if rows else None


class Store:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.raw_dir = data_dir / "raw"
        self.rejected_dir = data_dir / "rejected"
        self.staging_dir = data_dir / "staging"
        for folder in (self.data_dir, self.raw_dir, self.rejected_dir, self.staging_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = duckdb.connect(str(self.data_dir / DB_FILE))
        self._conn.execute(SCHEMA)
        self._conn.execute(MIGRATIONS)
        self._conn.execute(TRADE_VIEW)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def count_trades(self) -> int:
        with self._lock:
            row = _first(self._conn.execute("SELECT COUNT(*) FROM trades").fetchall())
        return int(row[0]) if row else 0

    def insert_frame(self, import_id: str, accepted: pl.DataFrame, base: str) -> tuple[int, int]:
        """Insert accepted trades in one Arrow batch. Returns (inserted, already_present).

        Rows whose trade_key already exists are skipped, which keeps re-imports idempotent.
        """
        if accepted.height == 0:
            return 0, 0
        incoming = accepted.select([name for name, _ in TRADE_DTYPES]).with_columns(
            pl.lit(import_id).alias("import_id"),
            pl.lit(base).alias("base_currency"),
        )
        columns = ", ".join(incoming.columns)
        insert = (
            f"INSERT INTO trades ({columns}) SELECT {columns} FROM {INCOMING} "
            "ON CONFLICT (trade_key) DO NOTHING"
        )
        with self._lock:
            before = self._count_locked()
            self._conn.register(INCOMING, incoming)
            try:
                self._conn.execute(insert)
            finally:
                self._conn.unregister(INCOMING)
            inserted = self._count_locked() - before
            if inserted:
                self._bump_version_locked()
        return inserted, accepted.height - inserted

    def insert_trades(self, import_id: str, trades: Sequence[Trade], base: str) -> tuple[int, int]:
        """Insert Trade objects. Kept for callers that build trades one at a time."""
        return self.insert_frame(import_id, frame_from_trades(trades), base)

    def insert_activity_events(self, import_id: str, events: Sequence[dict[str, Any]]) -> int:
        """Store source order/fill rows separately from matched trade summaries."""
        if not events:
            return 0
        rows = [
            {
                "event_key": hashlib.sha256(
                    f"{import_id}|{event['source_row']}".encode()
                ).hexdigest(),
                "import_id": import_id,
                **event,
            }
            for event in events
        ]
        incoming = pl.DataFrame(rows)
        names = ", ".join(incoming.columns)
        with self._lock:
            self._conn.register("incoming_activity_events", incoming)
            try:
                before = int(
                    self._conn.execute("SELECT COUNT(*) FROM activity_events").fetchall()[0][0]
                )
                self._conn.execute(
                    f"INSERT INTO activity_events ({names}) SELECT {names} "
                    "FROM incoming_activity_events ON CONFLICT (event_key) DO NOTHING"
                )
                after = int(
                    self._conn.execute("SELECT COUNT(*) FROM activity_events").fetchall()[0][0]
                )
            finally:
                self._conn.unregister("incoming_activity_events")
            inserted = after - before
            if inserted:
                self._bump_version_locked()
        return inserted

    def load_activity_frame(self, import_id: str | None = None) -> pl.DataFrame:
        """Imported source events, optionally limited to one import, in source-time order."""
        with self._lock:
            if import_id is None:
                relation = self._conn.sql(
                    "SELECT * FROM activity_events ORDER BY event_time, source_row"
                )
            else:
                relation = self._conn.sql(
                    "SELECT * FROM activity_events WHERE import_id = ? "
                    "ORDER BY event_time, source_row",
                    params=[import_id],
                )
            return relation.pl()  # pyright: ignore

    def _count_locked(self) -> int:
        row = _first(self._conn.execute("SELECT COUNT(*) FROM trades").fetchall())
        return int(row[0]) if row else 0

    def query_page(
        self,
        where: str,
        params: list[Any],
        order: str,
        limit: int,
        offset: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        """One page of trades and the total that match.

        `where` and `order` are built in queries.py from whitelisted columns.
        """
        with self._lock:
            total_rows = self._conn.execute(
                f"SELECT COUNT(*) FROM trade_view{where}", params
            ).fetchall()
            total = int(total_rows[0][0])
            result = self._conn.execute(
                f"SELECT * FROM trade_view{where} {order} LIMIT ? OFFSET ?",
                [*params, limit, offset],
            )
            names = [column[0] for column in cast(list[tuple[str, ...]], result.description)]
            rows = result.fetchall()
        return total, [dict(zip(names, row, strict=True)) for row in rows]

    def position_of(
        self, trade_key: str, where: str, params: list[Any], order: str
    ) -> tuple[int, int] | None:
        """(zero-based row index, total rows) of one trade in a filtered, sorted listing.

        None when the trade does not match the filters. `where` and `order` are built in
        queries.py from whitelisted columns.
        """
        with self._lock:
            total = int(
                self._conn.execute(f"SELECT COUNT(*) FROM trade_view{where}", params).fetchall()[0][
                    0
                ]
            )
            row = _first(
                self._conn.execute(
                    f"SELECT position FROM (SELECT trade_key, "
                    f"row_number() OVER ({order}) - 1 AS position FROM trade_view{where}) "
                    f"WHERE trade_key = ?",
                    [*params, trade_key],
                ).fetchall()
            )
        return (int(row[0]), total) if row else None

    def get_trade(self, trade_key: str) -> dict[str, Any] | None:
        with self._lock:
            result = self._conn.execute("SELECT * FROM trade_view WHERE trade_key = ?", [trade_key])
            names = [column[0] for column in cast(list[tuple[str, ...]], result.description)]
            rows = result.fetchall()
        return dict(zip(names, rows[0], strict=True)) if rows else None

    def update_trade(self, trade_key: str, fields: dict[str, str | None]) -> bool:
        """Set user-editable fields on one trade. Returns False when the trade does not exist.

        The dataset version changes, so cached analysis that depends on tags or emotions is
        rebuilt on the next request.
        """
        if not fields:
            return True
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._lock:
            found = self._conn.execute(
                "SELECT COUNT(*) FROM trades WHERE trade_key = ?", [trade_key]
            ).fetchall()
            if int(found[0][0]) == 0:
                return False
            values: list[Any] = [
                ("" if value is None and name == "notes" else value)
                for name, value in fields.items()
            ]
            self._conn.execute(
                f"UPDATE trades SET {assignments} WHERE trade_key = ?", [*values, trade_key]
            )
            self._bump_version_locked()
        return True

    def distinct_values(self, column: str) -> list[str]:
        """Distinct non-empty values of one trade column, for filter menus."""
        if column not in {"account", "symbol", "setup", "side", "tags", "emotion"}:
            raise ValueError(f"Cannot list values of '{column}'.")
        with self._lock:
            rows = self._conn.execute(
                f"SELECT DISTINCT {column} FROM trades "
                f"WHERE {column} IS NOT NULL AND {column} <> '' "
                f"ORDER BY {column}"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def list_views(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, config_json, updated_at FROM saved_views ORDER BY name"
            ).fetchall()
        return [
            {"name": r[0], "config": json.loads(r[1]), "updated_at": r[2].isoformat()} for r in rows
        ]

    def save_view(self, name: str, config: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO saved_views VALUES (?, ?, ?) ON CONFLICT (name) DO UPDATE SET "
                "config_json = excluded.config_json, updated_at = excluded.updated_at",
                [name, json.dumps(config), datetime.now(UTC).replace(tzinfo=None)],
            )

    def delete_view(self, name: str) -> bool:
        with self._lock:
            found = self._conn.execute(
                "SELECT COUNT(*) FROM saved_views WHERE name = ?", [name]
            ).fetchall()
            if int(found[0][0]) == 0:
                return False
            self._conn.execute("DELETE FROM saved_views WHERE name = ?", [name])
        return True

    def load_frame(self) -> pl.DataFrame:
        """All trades with derived fields, in exit-time order, as a Polars frame."""
        with self._lock:
            # DuckDB ships no type for .pl(). The result is always a Polars frame.
            relation = self._conn.sql("SELECT * FROM trade_view ORDER BY exit_time, trade_key")
            return relation.pl()  # pyright: ignore

    def dataset_version(self) -> str:
        """Changes whenever trades or settings change. Analysis caches key on it."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT value FROM settings WHERE key = 'dataset_version'"
            ).fetchall()
        return rows[0][0] if rows else "0"

    def _bump_version_locked(self) -> None:
        self._conn.execute(
            "INSERT INTO settings VALUES ('dataset_version', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [uuid.uuid4().hex],
        )

    def list_trades(self, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._lock:
            result = self._conn.execute(
                "SELECT * FROM trade_view ORDER BY exit_time, trade_key LIMIT ? OFFSET ?",
                [limit, offset],
            )
            names = [column[0] for column in cast(list[tuple[str, ...]], result.description)]
            rows = result.fetchall()
        return [dict(zip(names, row, strict=True)) for row in rows]

    def save_coach_report(
        self,
        report_id: str,
        dataset_version: str,
        filter_key: str,
        params_key: str,
        report_json: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO coach_reports VALUES (?, ?, ?, ?, ?, ?)",
                [
                    report_id,
                    dataset_version,
                    filter_key,
                    params_key,
                    datetime.now(UTC).replace(tzinfo=None),
                    report_json,
                ],
            )

    def find_coach_report(
        self, dataset_version: str, filter_key: str, params_key: str
    ) -> str | None:
        """A stored report for exactly this data, filters, and parameters, if there is one."""
        with self._lock:
            row = _first(
                self._conn.execute(
                    "SELECT report_json FROM coach_reports WHERE dataset_version = ? "
                    "AND filter_key = ? AND params_key = ? ORDER BY created_at DESC LIMIT 1",
                    [dataset_version, filter_key, params_key],
                ).fetchall()
            )
        return str(row[0]) if row else None

    def latest_coach_report(self, filter_key: str) -> str | None:
        """The most recent stored report for these filters, whatever the data version."""
        with self._lock:
            row = _first(
                self._conn.execute(
                    "SELECT report_json FROM coach_reports WHERE filter_key = ? "
                    "ORDER BY created_at DESC, report_id LIMIT 1",
                    [filter_key],
                ).fetchall()
            )
        return str(row[0]) if row else None

    def get_coach_report(self, report_id: str) -> str | None:
        with self._lock:
            row = _first(
                self._conn.execute(
                    "SELECT report_json FROM coach_reports WHERE report_id = ?", [report_id]
                ).fetchall()
            )
        return str(row[0]) if row else None

    def list_coach_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT report_id, dataset_version, filter_key, created_at FROM coach_reports "
                "ORDER BY created_at DESC LIMIT ?",
                [limit],
            ).fetchall()
        return [
            {
                "report_id": row[0],
                "dataset_version": row[1],
                "filter_key": row[2],
                "created_at": row[3].isoformat() + "Z",
            }
            for row in rows
        ]

    def latest_import(self) -> dict[str, Any] | None:
        """The most recent import record, used to describe the first steps of a Coach run."""
        records = self.list_imports()
        return self.get_import(str(records[0]["import_id"])) if records else None

    def get_setting(self, key: str) -> str | None:
        with self._lock:
            rows = self._conn.execute("SELECT value FROM settings WHERE key = ?", [key]).fetchall()
        return str(rows[0][0]) if rows else None

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self._bump_version_locked()
            self._conn.execute(
                "INSERT INTO settings VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                [key, value],
            )

    # ----- preferences, templates, wipe -----

    def get_preferences(self) -> dict[str, Any]:
        """Preferences saved with set_preference. They do not affect any analysis."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, value FROM settings WHERE key LIKE 'pref.%'"
            ).fetchall()
        return {str(key)[len("pref.") :]: json.loads(str(value)) for key, value in rows}

    def set_preference(self, name: str, value: Any) -> None:
        """Save a preference. Unlike set_setting this leaves the dataset version alone, so the
        analysis caches stay valid."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                [f"pref.{name}", json.dumps(value)],
            )

    def delete_setting(self, key: str) -> None:
        with self._lock:
            self._bump_version_locked()
            self._conn.execute("DELETE FROM settings WHERE key = ?", [key])

    def delete_template(self, fingerprint: str) -> bool:
        with self._lock:
            found = _first(
                self._conn.execute(
                    "SELECT 1 FROM mapping_templates WHERE fingerprint = ?", [fingerprint]
                ).fetchall()
            )
            if found is None:
                return False
            self._conn.execute("DELETE FROM mapping_templates WHERE fingerprint = ?", [fingerprint])
        return True

    def rename_template(self, fingerprint: str, name: str) -> bool:
        with self._lock:
            found = _first(
                self._conn.execute(
                    "SELECT 1 FROM mapping_templates WHERE fingerprint = ?", [fingerprint]
                ).fetchall()
            )
            if found is None:
                return False
            self._conn.execute(
                "UPDATE mapping_templates SET name = ?, updated_at = ? WHERE fingerprint = ?",
                [name, datetime.now(UTC).replace(tzinfo=None), fingerprint],
            )
        return True

    def wipe(self) -> dict[str, int]:
        """Delete every trade, import, view, template, report, setting, and stored file.

        The database file and folders stay, empty. Returns how much was removed.
        """
        removed: dict[str, int] = {}
        with self._lock:
            for table in (
                "trades",
                "imports",
                "saved_views",
                "coach_reports",
                "mapping_templates",
            ):
                row = _first(self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchall())
                removed[table] = int(row[0]) if row else 0
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.execute("DELETE FROM settings")
            self._bump_version_locked()
            self._conn.execute("CHECKPOINT")
        files = 0
        for folder in (self.raw_dir, self.rejected_dir, self.staging_dir):
            for path in folder.iterdir():
                if path.is_file():
                    path.unlink()
                    files += 1
        removed["files"] = files
        return removed

    def record_import(
        self, import_id: str, filename: str, sha256: str, record: dict[str, Any]
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO imports VALUES (?, ?, ?, ?, ?)",
                [
                    import_id,
                    filename,
                    sha256,
                    datetime.now(UTC).replace(tzinfo=None),
                    json.dumps(record),
                ],
            )

    def get_import(self, import_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = _first(
                self._conn.execute(
                    "SELECT import_id, filename, sha256, created_at, record_json "
                    "FROM imports WHERE import_id = ?",
                    [import_id],
                ).fetchall()
            )
        if row is None:
            return None
        record = cast(dict[str, Any], json.loads(row[4]))
        return {
            "import_id": row[0],
            "filename": row[1],
            "sha256": row[2],
            "created_at": row[3].isoformat(),
            **record,
        }

    def list_imports(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT import_id, filename, sha256, created_at "
                "FROM imports ORDER BY created_at DESC"
            ).fetchall()
        return [
            {"import_id": r[0], "filename": r[1], "sha256": r[2], "created_at": r[3].isoformat()}
            for r in rows
        ]

    def save_template(self, fingerprint: str, name: str, mapping: dict[str, str | None]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO mapping_templates VALUES (?, ?, ?, ?) "
                "ON CONFLICT (fingerprint) DO UPDATE SET name = excluded.name, "
                "mapping_json = excluded.mapping_json, updated_at = excluded.updated_at",
                [fingerprint, name, json.dumps(mapping), datetime.now(UTC).replace(tzinfo=None)],
            )

    def get_template(self, fingerprint: str) -> dict[str, str | None] | None:
        with self._lock:
            row = _first(
                self._conn.execute(
                    "SELECT mapping_json FROM mapping_templates WHERE fingerprint = ?",
                    [fingerprint],
                ).fetchall()
            )
        if row is None:
            return None
        return cast(dict[str, str | None], json.loads(row[0]))

    def list_templates(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT fingerprint, name, mapping_json, updated_at "
                "FROM mapping_templates ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {
                "fingerprint": r[0],
                "name": r[1],
                "mapping": json.loads(r[2]),
                "updated_at": r[3].isoformat(),
            }
            for r in rows
        ]
