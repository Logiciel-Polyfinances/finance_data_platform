from datetime import datetime

import pytest

import src.lambda_handlers.derived as derived
import src.lambda_handlers.fred_macro as fred_macro
import src.lambda_handlers.universe as universe_handler
from src.lambda_handlers.per_ticker import _ticker
from src.lambda_handlers.prices import MARKET_TZ, default_run_date, resolve_dates


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Scheduled 16:05 runs: Tuesday loads Monday, Monday loads the previous Friday.
        (datetime(2026, 9, 29, 16, 5, tzinfo=MARKET_TZ), "2026-09-28"),
        (datetime(2026, 9, 28, 16, 5, tzinfo=MARKET_TZ), "2026-09-25"),
        # Manual weekend run -> last weekday before it.
        (datetime(2026, 9, 27, 10, 0, tzinfo=MARKET_TZ), "2026-09-25"),
    ],
)
def test_default_run_date_matches_airflow_ds(now, expected):
    assert default_run_date(now).isoformat() == expected


def test_resolve_dates_fallbacks():
    now = datetime(2026, 9, 29, 16, 5, tzinfo=MARKET_TZ)
    assert resolve_dates({}, now) == ("2026-09-28", "2026-09-28")
    assert resolve_dates({"start_dt": "2020-01-01"}, now) == ("2020-01-01", "2020-01-01")
    assert resolve_dates({"start_dt": "2020-01-01", "end_dt": "2020-12-31"}, now) == (
        "2020-01-01",
        "2020-12-31",
    )
    assert resolve_dates({"start_dt": "", "end_dt": None}, now) == ("2026-09-28", "2026-09-28")


def test_per_ticker_event_validation():
    assert _ticker({"ticker": " aapl "}) == "AAPL"
    with pytest.raises(ValueError):
        _ticker({})


def test_get_tickers_handler(monkeypatch):
    seen = {}

    def _fake_resolve(mode, override=None, limit=0):
        seen.update(mode=mode, override=override, limit=limit)
        return ["AAPL"]

    monkeypatch.setattr(universe_handler, "resolve_tickers", _fake_resolve)

    # The prices state machine forwards its own input, which uses symbols_override.
    out = universe_handler.handler({"mode": "all", "symbols_override": "aapl", "limit_tickers": 3})

    assert out == {"tickers": ["AAPL"]}
    assert seen == {"mode": "all", "override": "aapl", "limit": 3}


def test_fred_series_resolution():
    from src.core.constants import FRED_COLUMN_SERIES

    assert fred_macro.resolve_series(None) == sorted(FRED_COLUMN_SERIES)
    assert fred_macro.resolve_series("None") == sorted(FRED_COLUMN_SERIES)
    assert fred_macro.resolve_series("CPI, gdp") == ["cpi", "gdp"]


def test_fred_series_handler_lists_series_for_the_map():
    assert fred_macro.series_handler({"series_override": "cpi,GDP"}) == {"series": ["cpi", "gdp"]}


def test_fred_handler_runs_one_series(monkeypatch):
    import src.orchestration.pipelines.run_macro as run_macro

    monkeypatch.setattr(run_macro, "run_macro_pipeline", lambda series: {"cpi": 5}[series])

    assert fred_macro.handler({"series": " CPI "}) == {"series": "cpi", "rows": 5}
    with pytest.raises(ValueError):
        fred_macro.handler({})


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"tickers": "aapl, msft"}, ["AAPL", "MSFT"]),
        ({"tickers": ["aapl"]}, ["AAPL"]),
        ({"tickers": "None"}, None),
        ({}, None),
        (None, None),
    ],
)
def test_ratios_handler_parses_tickers(monkeypatch, event, expected):
    import src.orchestration.pipelines.run_fundamental_ratios as run_ratios

    seen = []
    monkeypatch.setattr(
        run_ratios, "run_fundamental_ratios_pipeline", lambda tickers: seen.append(tickers) or 0
    )

    assert derived.ratios_handler(event) == {"rows": 0}
    assert seen == [expected]


def test_metrics_handler_parses_windows(monkeypatch):
    import src.orchestration.pipelines.run_metrics as run_metrics

    seen = []
    monkeypatch.setattr(run_metrics, "run_metrics_pipeline", lambda windows: seen.append(windows) or 0)

    derived.metrics_handler({"windows": "1Y,6m"})
    assert seen == [["1y", "6m"]]
