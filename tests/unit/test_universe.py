import pytest

import src.orchestration.universe as universe

_DB_UNIVERSE = ["AAPL", "SHOP.TO", "^GSPC", "MSFT", "RY.TO"]


@pytest.fixture(autouse=True)
def _fake_db(monkeypatch):
    monkeypatch.setattr(
        universe,
        "get_scheduled_tickers",
        lambda mode="all": universe._FILTERS[mode](_DB_UNIVERSE),
    )


def test_filters_match_former_dags():
    assert universe.filter_us(_DB_UNIVERSE) == ["AAPL", "MSFT"]
    assert universe.filter_non_us(_DB_UNIVERSE) == ["SHOP.TO", "RY.TO"]


def test_resolve_modes():
    assert universe.resolve_tickers("all") == _DB_UNIVERSE
    assert universe.resolve_tickers("us_only") == ["AAPL", "MSFT"]
    assert universe.resolve_tickers("non_us_only") == ["SHOP.TO", "RY.TO"]


def test_override_wins_and_is_normalized():
    assert universe.resolve_tickers("us_only", override=" sofi, shop.to ,") == ["SOFI", "SHOP.TO"]
    assert universe.resolve_tickers("all", override=["aapl"]) == ["AAPL"]


@pytest.mark.parametrize("override", [None, "", "None", "  ", []])
def test_empty_override_means_db_universe(override):
    assert universe.resolve_tickers("all", override=override) == _DB_UNIVERSE


def test_limit():
    assert universe.resolve_tickers("all", limit=2) == ["AAPL", "SHOP.TO"]


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        universe.resolve_tickers("fred_series")


def test_parse_override_custom_normalization():
    assert universe.parse_override(" CPI, gdp ,", normalize=str.lower) == ["cpi", "gdp"]
    assert universe.parse_override("none", normalize=str.lower) == []
