import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

import src.api.deps as deps
import src.api.routes.fundamentals as fundamentals_router
import src.api.routes.instruments as instruments_router
import src.api.routes.macro as macro_router
import src.api.routes.prices as prices_router
from src.core.database import get_db
from src.main import app


class _FakeInstrument:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _instrument(**overrides):
    defaults = {
        "id": 1,
        "ticker": "SOFI",
        "name": "SoFi Technologies",
        "exchange": "NMS",
        "currency": "USD",
        "timezone": "America/New_York",
        "is_active": True,
        "is_scheduled": True,
    }
    defaults.update(overrides)
    return _FakeInstrument(**defaults)


@pytest.fixture(autouse=True)
def _override_get_db():
    app.dependency_overrides[get_db] = lambda: iter([None])
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _disable_cache(monkeypatch):
    """The routes call cache_get_json/cache_set_json unconditionally; without
    this, tests would depend on whatever REDIS_URL happens to be in the local
    .env (or hang on a connection timeout when nothing's listening there).
    """
    for module in (prices_router, fundamentals_router, macro_router, instruments_router):
        monkeypatch.setattr(module, "cache_get_json", lambda key: None)
        monkeypatch.setattr(module, "cache_set_json", lambda key, value, ttl_seconds=60: None)


@pytest.fixture
def client():
    return TestClient(app)


def test_list_instruments(monkeypatch, client):
    monkeypatch.setattr(
        instruments_router,
        "list_instruments",
        lambda db, is_active=None, is_scheduled=None, limit=None, offset=0: [_instrument()],
    )
    monkeypatch.setattr(
        instruments_router, "count_instruments", lambda db, is_active=None, is_scheduled=None: 1
    )

    resp = client.get("/v1/instruments")

    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"
    assert resp.json() == [
        {
            "id": 1,
            "ticker": "SOFI",
            "name": "SoFi Technologies",
            "exchange": "NMS",
            "currency": "USD",
            "timezone": "America/New_York",
            "is_active": True,
            "is_scheduled": True,
        }
    ]


def test_get_instrument_404(monkeypatch, client):
    monkeypatch.setattr(instruments_router, "get_instrument", lambda db, ticker: None)

    resp = client.get("/v1/instruments/NOTREAL")

    assert resp.status_code == 404


def test_get_instrument_found(monkeypatch, client):
    monkeypatch.setattr(instruments_router, "get_instrument", lambda db, ticker: _instrument())

    resp = client.get("/v1/instruments/SOFI")

    assert resp.status_code == 200
    assert resp.json()["ticker"] == "SOFI"


def _fake_upsert(ticker, is_scheduled=True):
    return {
        "id": 1,
        "ticker": ticker,
        "name": "SoFi Technologies",
        "exchange": "NMS",
        "currency": "USD",
        "timezone": "America/New_York",
        "is_active": True,
        "is_scheduled": is_scheduled,
    }


@pytest.fixture
def backfills(monkeypatch):
    """Step Functions unconfigured and dedup locks free by default; records
    both the in-process fallbacks and any StartExecution calls."""
    calls = {"register": [], "fundamentals": [], "sfn": []}
    for name in ("prices_state_machine_arn", "fanout_state_machine_arn", "sec_fundamentals_function_arn"):
        monkeypatch.setattr(instruments_router.settings, name, None)
    monkeypatch.setattr(instruments_router, "try_acquire_lock", lambda name, ttl_seconds: True)
    monkeypatch.setattr(
        instruments_router,
        "register_ticker",
        lambda ticker, **kwargs: calls["register"].append({"ticker": ticker, **kwargs}),
    )
    monkeypatch.setattr(
        instruments_router, "run_fundamentals_pipeline", lambda ticker: calls["fundamentals"].append(ticker)
    )

    class _FakeSfn:
        def start_execution(self, stateMachineArn, input):
            calls["sfn"].append((stateMachineArn, json.loads(input)))

    monkeypatch.setattr(instruments_router, "_sfn_client", lambda: _FakeSfn())
    return calls


def _configure_sfn(monkeypatch):
    monkeypatch.setattr(instruments_router.settings, "prices_state_machine_arn", "arn:prices")
    monkeypatch.setattr(instruments_router.settings, "fanout_state_machine_arn", "arn:fanout")
    monkeypatch.setattr(instruments_router.settings, "sec_fundamentals_function_arn", "arn:sec")


def test_create_instrument_runs_backfills_in_process_without_step_functions(monkeypatch, client, backfills):
    monkeypatch.setattr(instruments_router, "validate_and_upsert_ticker", _fake_upsert)

    resp = client.post("/v1/instruments", json={"ticker": "sofi", "is_scheduled": False})

    assert resp.status_code == 202
    assert resp.json()["ticker"] == "sofi"
    # TestClient runs BackgroundTasks inline, so the fallbacks have fired.
    assert backfills["register"] == [
        {"ticker": "SOFI", "is_scheduled": False, "backfill_start": "2015-01-01", "backfill_end": None}
    ]
    assert backfills["fundamentals"] == ["SOFI"]
    assert backfills["sfn"] == []


def test_create_instrument_starts_step_functions_and_skips_in_process(monkeypatch, client, backfills):
    monkeypatch.setattr(instruments_router, "validate_and_upsert_ticker", _fake_upsert)
    _configure_sfn(monkeypatch)

    resp = client.post("/v1/instruments", json={"ticker": "sofi", "backfill_start": "2020-01-01"})

    assert resp.status_code == 202
    by_arn = dict(backfills["sfn"])
    # A missing backfill_end is pinned to today, not left to the state
    # machine's single-day fallback.
    assert by_arn["arn:prices"] == {
        "symbols_override": "SOFI",
        "start_dt": "2020-01-01",
        "end_dt": date.today().isoformat(),
    }
    assert by_arn["arn:fanout"] == {"mode": "us_only", "run_function": "arn:sec", "tickers_override": "SOFI"}
    assert backfills["register"] == []
    assert backfills["fundamentals"] == []


def test_create_instrument_503_when_step_functions_rejects(monkeypatch, client, backfills):
    from botocore.exceptions import ClientError

    monkeypatch.setattr(instruments_router, "validate_and_upsert_ticker", _fake_upsert)
    _configure_sfn(monkeypatch)

    class _FailingSfn:
        def start_execution(self, **kwargs):
            raise ClientError(
                {"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "StartExecution"
            )

    monkeypatch.setattr(instruments_router, "_sfn_client", lambda: _FailingSfn())

    resp = client.post("/v1/instruments", json={"ticker": "sofi"})

    assert resp.status_code == 503
    assert backfills["register"] == []


def test_refresh_404_for_unregistered_ticker(monkeypatch, client, backfills):
    monkeypatch.setattr(instruments_router, "get_instrument", lambda db, ticker: None)

    resp = client.post("/v1/instruments/NOPE/refresh", json={})

    assert resp.status_code == 404


def test_refresh_triggers_requested_datasets(monkeypatch, client, backfills):
    monkeypatch.setattr(instruments_router, "get_instrument", lambda db, ticker: _instrument())

    resp = client.post("/v1/instruments/sofi/refresh", json={"datasets": ["prices"]})

    assert resp.status_code == 202
    assert resp.json() == {"ticker": "SOFI", "triggered": [{"dataset": "prices", "executor": "in_process"}]}
    assert backfills["fundamentals"] == []


def test_refresh_via_step_functions(monkeypatch, client, backfills):
    monkeypatch.setattr(instruments_router, "get_instrument", lambda db, ticker: _instrument())
    _configure_sfn(monkeypatch)

    resp = client.post("/v1/instruments/SOFI/refresh", json={"backfill_end": "2024-12-31"})

    assert resp.status_code == 202
    assert [j["executor"] for j in resp.json()["triggered"]] == ["step_functions", "step_functions"]
    assert dict(backfills["sfn"])["arn:prices"]["end_dt"] == "2024-12-31"


def test_refresh_409_when_all_datasets_already_in_flight(monkeypatch, client, backfills):
    monkeypatch.setattr(instruments_router, "get_instrument", lambda db, ticker: _instrument())
    monkeypatch.setattr(instruments_router, "try_acquire_lock", lambda name, ttl_seconds: False)

    resp = client.post("/v1/instruments/SOFI/refresh", json={})

    assert resp.status_code == 409


def test_create_instrument_rejects_invalid_ticker(monkeypatch, client):
    def _raise(ticker, is_scheduled=True):
        raise ValueError(f"'{ticker}' does not look like a real Yahoo Finance ticker")

    monkeypatch.setattr(instruments_router, "validate_and_upsert_ticker", _raise)

    resp = client.post("/v1/instruments", json={"ticker": "NOTATICKER"})

    assert resp.status_code == 422


def test_update_scheduled_404(monkeypatch, client):
    monkeypatch.setattr(instruments_router, "set_scheduled", lambda db, ticker, is_scheduled: None)

    resp = client.patch("/v1/instruments/NOTREAL/scheduled", json={"is_scheduled": False})

    assert resp.status_code == 404


def test_update_scheduled_ok(monkeypatch, client):
    monkeypatch.setattr(
        instruments_router,
        "set_scheduled",
        lambda db, ticker, is_scheduled: _instrument(is_scheduled=is_scheduled),
    )

    resp = client.patch("/v1/instruments/SOFI/scheduled", json={"is_scheduled": False})

    assert resp.status_code == 200
    assert resp.json()["is_scheduled"] is False


def test_get_prices_404_for_unregistered_ticker(monkeypatch, client):
    monkeypatch.setattr(prices_router, "get_instrument", lambda db, ticker: None)

    resp = client.get("/v1/prices/NOTREAL")

    assert resp.status_code == 404


def test_get_prices_returns_rows(monkeypatch, client):
    monkeypatch.setattr(prices_router, "get_instrument", lambda db, ticker: _instrument())
    row = _FakeInstrument(
        symbol="SOFI",
        ts=date(2026, 1, 2),
        open=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        volume=1000,
        close_returns=0.01,
    )
    monkeypatch.setattr(
        prices_router,
        "get_prices",
        lambda db, ticker, start=None, end=None, limit=500, offset=0, sort_by="ts", order="desc": [row],
    )
    monkeypatch.setattr(prices_router, "count_prices", lambda db, ticker, start=None, end=None: 1)

    resp = client.get("/v1/prices/SOFI")

    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"
    assert resp.json() == [
        {
            "symbol": "SOFI",
            "ts": "2026-01-02",
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "volume": 1000,
            "close_returns": 0.01,
        }
    ]


def test_get_fundamentals_404_for_unregistered_ticker(monkeypatch, client):
    monkeypatch.setattr(fundamentals_router, "get_instrument", lambda db, ticker: None)

    resp = client.get("/v1/fundamentals/NOTREAL")

    assert resp.status_code == 404


def test_get_fundamentals_returns_rows(monkeypatch, client):
    monkeypatch.setattr(fundamentals_router, "get_instrument", lambda db, ticker: _instrument())
    row = _FakeInstrument(
        ticker="SOFI",
        concept="us-gaap:Revenues",
        unit="USD",
        period_end=date(2025, 12, 31),
        fy=2025,
        fp="FY",
        form="10-K",
        val=1000.0,
    )
    monkeypatch.setattr(
        fundamentals_router,
        "get_fundamentals",
        lambda db,
        ticker,
        concept=None,
        concepts=None,
        form=None,
        period=None,
        limit=500,
        offset=0,
        sort_by="period_end",
        order="desc": [row],
    )
    monkeypatch.setattr(
        fundamentals_router,
        "count_fundamentals",
        lambda db, ticker, concept=None, concepts=None, form=None, period=None: 1,
    )

    resp = client.get("/v1/fundamentals/SOFI")

    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"
    assert resp.json()[0]["concept"] == "us-gaap:Revenues"


def test_health_does_not_require_api_key(monkeypatch, client):
    monkeypatch.setattr(deps.settings, "environment", "prod")
    monkeypatch.setattr(deps.settings, "api_key", "secret123")

    class _FakeSession:
        def execute(self, *args, **kwargs):
            return None

    def _fake_get_db():
        yield _FakeSession()

    app.dependency_overrides[get_db] = _fake_get_db

    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_instruments_route_enforces_api_key_when_configured(monkeypatch, client):
    monkeypatch.setattr(deps.settings, "environment", "prod")
    monkeypatch.setattr(deps.settings, "api_key", "secret123")
    monkeypatch.setattr(
        instruments_router,
        "list_instruments",
        lambda db, is_active=None, is_scheduled=None, limit=None, offset=0: [],
    )
    monkeypatch.setattr(
        instruments_router, "count_instruments", lambda db, is_active=None, is_scheduled=None: 0
    )

    resp_no_key = client.get("/v1/instruments")
    resp_with_key = client.get("/v1/instruments", headers={"X-API-Key": "secret123"})

    assert resp_no_key.status_code == 401
    assert resp_with_key.status_code == 200


def test_health_returns_503_when_db_is_unreachable(client):
    def _fake_get_db():
        class _BrokenSession:
            def execute(self, *args, **kwargs):
                raise RuntimeError("connection refused")

        yield _BrokenSession()

    app.dependency_overrides[get_db] = _fake_get_db

    resp = client.get("/health")

    assert resp.status_code == 503
    assert "database unavailable" in resp.json()["detail"]


def test_missing_api_key_is_checked_before_body_validation(monkeypatch, client):
    """Auth dependencies (require_write -> authenticate) run before the route
    handler, so a missing key on a mutating route must short-circuit to 401
    -- not fall through to a 422 on the (also-invalid) request body.
    """
    monkeypatch.setattr(deps.settings, "environment", "prod")
    monkeypatch.setattr(deps.settings, "api_key", "secret123")

    resp = client.post("/v1/instruments", json={})  # missing required "ticker" field too

    assert resp.status_code == 401


def test_get_macro_series_rejects_unknown_series(client):
    resp = client.get("/v1/macro/not-a-real-series")

    assert resp.status_code == 404


def test_get_macro_series_accepts_slash_containing_series(monkeypatch, client):
    """Regression: {series} used to be a plain path param, which Starlette
    never matches across a "/" -- routes like /macro/usd/cad (a real
    FRED_COLUMN_SERIES key) 404'd even though the series is valid. Fixed via
    {series:path}.
    """
    row = _FakeInstrument(series="usd/cad", ts=date(2026, 1, 1), value=1.35)
    monkeypatch.setattr(
        macro_router,
        "get_macro_series",
        lambda db, series, start=None, end=None, limit=500, offset=0, order="asc": [row],
    )
    monkeypatch.setattr(macro_router, "count_macro_series", lambda db, series, start=None, end=None: 1)

    resp = client.get("/v1/macro/usd/cad")

    assert resp.status_code == 200
    assert resp.json()[0]["series"] == "usd/cad"


def test_get_macro_series_returns_rows(monkeypatch, client):
    row = _FakeInstrument(series="cpi", ts=date(2026, 1, 1), value=3.1)
    monkeypatch.setattr(
        macro_router,
        "get_macro_series",
        lambda db, series, start=None, end=None, limit=500, offset=0, order="asc": [row],
    )
    monkeypatch.setattr(macro_router, "count_macro_series", lambda db, series, start=None, end=None: 1)

    resp = client.get("/v1/macro/cpi")

    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"
    assert resp.json() == [{"series": "cpi", "ts": "2026-01-01", "value": 3.1}]


def test_get_instrument_figi_404_for_unregistered_ticker(monkeypatch, client):
    monkeypatch.setattr(instruments_router, "get_instrument", lambda db, ticker: None)

    resp = client.get("/v1/instruments/NOTREAL/figi")

    assert resp.status_code == 404


def test_get_instrument_figi_returns_all_candidates(monkeypatch, client):
    monkeypatch.setattr(instruments_router, "get_instrument", lambda db, ticker: _instrument())
    rows = [
        _FakeInstrument(
            ticker="SOFI",
            figi="FIGI1",
            composite_figi=None,
            share_class_figi=None,
            security_type=None,
            market_sector=None,
            exch_code="US",
            name=None,
        ),
        _FakeInstrument(
            ticker="SOFI",
            figi="FIGI2",
            composite_figi=None,
            share_class_figi=None,
            security_type=None,
            market_sector=None,
            exch_code="LN",
            name=None,
        ),
    ]
    monkeypatch.setattr(instruments_router, "get_figi_mappings", lambda db, ticker: rows)

    resp = client.get("/v1/instruments/SOFI/figi")

    assert resp.status_code == 200
    assert [r["figi"] for r in resp.json()] == ["FIGI1", "FIGI2"]


def test_unhandled_exception_returns_generic_500(monkeypatch):
    def _boom(db, ticker):
        raise RuntimeError("boom: something internal broke")

    monkeypatch.setattr(instruments_router, "get_instrument", _boom)

    # TestClient's default raise_server_exceptions=True re-raises after the
    # exception handler already sent its response (Starlette's
    # ServerErrorMiddleware does this deliberately, so bugs aren't hidden
    # during testing) -- disable it here to assert on the response instead.
    no_raise_client = TestClient(app, raise_server_exceptions=False)
    resp = no_raise_client.get("/v1/instruments/SOFI")

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}
    assert "boom" not in resp.text
