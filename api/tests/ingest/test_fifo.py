from datetime import UTC, datetime

from obsidian_ledger.ingest.fifo import Fill, pair_fills


def _fill(
    row: int,
    side: str,
    qty: float,
    price: float,
    hour: int,
    commission: float = 0.0,
    multiplier: float = 1.0,
    symbol: str = "AAPL",
) -> Fill:
    assert side in ("long", "short")
    return Fill(
        row=row,
        account="U1",
        symbol=symbol,
        asset_class="stock",
        currency="USD",
        side=side,  # type: ignore[arg-type]
        qty=qty,
        price=price,
        time=datetime(2026, 1, 6, hour, row, tzinfo=UTC),
        commission=commission,
        multiplier=multiplier,
        order_id=f"O{row}",
        has_offset=False,
    )


def test_long_round_trip_splits_commission_between_both_fills() -> None:
    legs, remainders = pair_fills(
        [
            _fill(1, "long", 20, 189.20, 14, commission=-1.0),
            _fill(2, "short", 20, 190.40, 16, commission=-1.0),
        ]
    )
    assert remainders == []
    assert len(legs) == 1
    leg = legs[0]
    assert leg.qty == 20
    assert leg.open_fill.price == 189.20
    assert leg.close_fill.price == 190.40
    assert round(leg.commission, 6) == -2.0


def test_scale_out_produces_one_leg_per_closing_piece_oldest_first() -> None:
    legs, remainders = pair_fills(
        [
            _fill(1, "long", 10, 100.0, 14),
            _fill(2, "long", 10, 110.0, 15),
            _fill(3, "short", 5, 120.0, 16),
            _fill(4, "short", 15, 130.0, 17),
        ]
    )
    assert remainders == []
    # The first short closes 5 of lot 1. The second closes the last 5 of lot 1 and all of lot 2.
    assert [(leg.open_fill.row, leg.qty) for leg in legs] == [(1, 5), (1, 5), (2, 10)]
    gross = [(leg.close_fill.price - leg.open_fill.price) * leg.qty for leg in legs]
    assert gross == [100.0, 150.0, 200.0]
    assert sum(gross) == 450.0


def test_short_round_trip_uses_sell_first() -> None:
    legs, _ = pair_fills(
        [
            _fill(1, "short", 2, 21450.0, 15, multiplier=2.0, symbol="MNQ", commission=-2.4),
            _fill(2, "long", 2, 21480.0, 15, multiplier=2.0, symbol="MNQ", commission=-2.4),
        ]
    )
    assert len(legs) == 1
    leg = legs[0]
    assert leg.open_fill.side == "short"
    gross = (leg.open_fill.price - leg.close_fill.price) * leg.qty * leg.open_fill.multiplier
    assert gross == -120.0
    assert round(leg.commission, 6) == -4.8


def test_open_position_is_reported_not_paired() -> None:
    legs, remainders = pair_fills(
        [
            _fill(1, "long", 10, 50.0, 14),
            _fill(2, "long", 4, 51.0, 15),
            _fill(3, "short", 6, 52.0, 16),
        ]
    )
    assert len(legs) == 1
    assert [(r.side, r.qty) for r in remainders] == [("long", 8.0)]


def test_flat_then_reverse_opens_new_position_in_fill_direction() -> None:
    legs, remainders = pair_fills(
        [
            _fill(1, "long", 5, 10.0, 14),
            _fill(2, "short", 8, 11.0, 15),
        ]
    )
    assert len(legs) == 1
    assert legs[0].qty == 5
    assert [(r.side, r.qty) for r in remainders] == [("short", 3.0)]
