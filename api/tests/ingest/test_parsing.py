from datetime import datetime

from obsidian_ledger.ingest.canonical import assign_fields, header_matches, normalize_header
from obsidian_ledger.ingest.parse import (
    SLASH_DAYFIRST,
    SLASH_MONTHFIRST,
    choose_date_format,
    count_number_style,
    parse_number,
    parse_side,
    parse_time,
)


def test_header_normalization_splits_symbols_and_punctuation() -> None:
    assert normalize_header("S/L") == "s l"
    assert normalize_header("Net P&L USD") == "net p l usd"
    assert normalize_header("Position size (qty)") == "position size qty"
    assert normalize_header("ClientAccountID") == "clientaccountid"


def test_mt5_headers_map_to_canonical_fields_with_high_confidence() -> None:
    headers = [
        "Ticket",
        "Open Time",
        "Type",
        "Size",
        "Item",
        "S/L",
        "Close Time",
        "Commission",
        "Profit",
    ]
    mapped = {index: match.field for index, match in assign_fields(headers, set(), set()).items()}
    assert mapped == {
        0: "trade_id",
        1: "entry_time",
        2: "side",
        3: "qty",
        4: "symbol",
        5: "stop_loss",
        6: "exit_time",
        7: "commission",
        8: "gross_pnl",
    }
    assert header_matches("Open Time")["entry_time"].confidence == "high"


def test_fuzzy_match_is_low_confidence() -> None:
    match = header_matches("Qantity")["qty"]
    assert match.confidence == "low"


def test_each_field_is_assigned_once() -> None:
    chosen = assign_fields(["Price", "Price (2)"], set(), set())
    assert len(chosen) <= 1


def test_number_parsing_respects_decimal_style_and_currency_signs() -> None:
    assert parse_number("2.468,50", "comma") == 2468.5
    assert parse_number("1,08500", "comma") == 1.085
    assert parse_number("1,234.50", "dot") == 1234.5
    assert parse_number("$1,234.50", "dot") == 1234.5
    assert parse_number("€ 2.000,00", "comma") == 2000.0
    assert parse_number("(12.50)", "dot") == -12.5
    assert parse_number("-0.70", "dot") == -0.7
    assert parse_number("abc", "dot") is None
    assert parse_number("", "dot") is None


def test_decimal_style_vote_ignores_ambiguous_three_digit_values() -> None:
    style, comma, dot = count_number_style(["2.468,50", "1,08500", "189.20", "1,085"])
    assert style == "comma"
    assert (comma, dot) == (2, 1)
    assert count_number_style(["1,234.56", "10.5"])[0] == "dot"


def test_side_words() -> None:
    assert parse_side("BUY") == "long"
    assert parse_side("Entry long") == "long"
    assert parse_side("Exit short") == "short"
    assert parse_side("sell") == "short"
    assert parse_side("hold") is None


def test_time_formats_and_offsets() -> None:
    parsed = parse_time("2026.01.06 14:32:01", None)
    assert parsed == (datetime(2026, 1, 6, 14, 32, 1), False)
    aware = parse_time("2026-01-06T14:32:00Z", None)
    assert aware is not None
    assert aware[0].tzinfo is not None
    assert aware[1] is True
    assert parse_time("20260106;143205", None) == (datetime(2026, 1, 6, 14, 32, 5), False)


def test_impossible_dates_are_not_parsed() -> None:
    assert parse_time("32.13.2026 11:00", None) is None


def test_slash_dates_need_a_family() -> None:
    assert parse_time("01/06/2026 10:00", None) is None
    dayfirst = parse_time("01/06/2026 10:00", SLASH_DAYFIRST)
    monthfirst = parse_time("01/06/2026 10:00", SLASH_MONTHFIRST)
    assert dayfirst is not None and dayfirst[0].month == 6
    assert monthfirst is not None and monthfirst[0].month == 1


def test_ambiguous_slash_dates_are_detected() -> None:
    choice = choose_date_format(["01/06/2026 10:00", "01/07/2026 10:00"])
    assert choice.ambiguous is True
    choice = choose_date_format(["13/06/2026 10:00", "21/07/2026 10:00"])
    assert choice.ambiguous is False
    assert choice.slash_family == SLASH_DAYFIRST
