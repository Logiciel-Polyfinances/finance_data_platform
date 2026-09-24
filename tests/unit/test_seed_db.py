from scripts.seed_db import BENCHMARKS, iter_seed_entries


def test_benchmarks_present_with_expected_currency():
    by_ticker = {b["ticker"]: b for b in BENCHMARKS}
    assert by_ticker["^GSPC"]["currency"] == "USD"
    assert by_ticker["^GSPTSE"]["currency"] == "CAD"


def test_seed_entries_unique_and_well_formed():
    entries = iter_seed_entries()
    tickers = [e["ticker"] for e in entries]
    assert len(tickers) == len(set(tickers))

    required = {"ticker", "name", "exchange", "currency", "timezone"}
    for e in entries:
        assert required <= e.keys()

    # TSX names are CAD-denominated ".TO" suffixes
    for e in entries:
        if e["ticker"].endswith(".TO"):
            assert e["currency"] == "CAD"


def test_benchmarks_only_returns_just_benchmarks():
    assert iter_seed_entries(benchmarks_only=True) == BENCHMARKS
