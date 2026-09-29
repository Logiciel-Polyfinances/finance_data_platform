"""End-to-end tests against a REAL Postgres + Redis (no DB mocking).

Exercises the full HTTP -> FastAPI -> SQLAlchemy -> Postgres path plus real
Redis for rate limiting and dedup locks -- the things the unit suite (which
mocks the DB) can't cover: scopes read back from the DB, 403 scope gating,
429 rate limiting, and 409 idempotence on a real lock. (Redis only exists in
the local docker stack; in AWS the limiter and locks fail open and API Gateway
throttling takes over.)

Only truly-external calls (Yahoo/SEC ingestion, Step Functions) are stubbed.

Run it with infra up and env pointed at it, e.g.:
    FDP_E2E=1 ENV=prod \
    DATABASE_URL=postgresql+psycopg2://finance:finance@localhost:15432/finance \
    REDIS_URL=redis://localhost:56379/0 API_KEY=master-e2e-key BUCKET_ID=e2e \
    RATE_LIMIT_PER_MINUTE=1000 RATE_LIMIT_WRITE_PER_MINUTE=3 \
    uv run pytest tests/integration -q

Skipped unless FDP_E2E=1 so a plain `pytest tests` on a dev box doesn't fail
for want of a database.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("FDP_E2E") != "1", reason="requires live Postgres+Redis (set FDP_E2E=1)"
)

MASTER_KEY = os.getenv("API_KEY", "master-e2e-key")


@pytest.fixture(scope="module")
def app_modules():
    """Import app + collaborators after env is set (engine binds at import)."""
    import src.api.routes.instruments as instruments_router
    from src.core.cache import get_redis_client
    from src.main import app

    # Start from a clean Redis so leftover buckets/locks from a previous run
    # don't skew rate-limit/idempotence assertions.
    client = get_redis_client()
    assert client is not None, "Redis must be reachable for the E2E suite"
    client.flushall()

    return app, instruments_router


@pytest.fixture()
def client(app_modules):
    from fastapi.testclient import TestClient

    app, _ = app_modules
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stub_external(app_modules, monkeypatch):
    """Stub the external ingestion + Step Functions calls so no real
    Yahoo/SEC/AWS traffic happens. The DB and Redis are left real."""
    _, instruments_router = app_modules

    def _fake_upsert(ticker, is_scheduled=True):
        return {
            "id": 1,
            "ticker": ticker.upper(),
            "name": "Stubbed Co",
            "exchange": "NMS",
            "currency": "USD",
            "timezone": "America/New_York",
            "is_active": True,
            "is_scheduled": is_scheduled,
        }

    monkeypatch.setattr(instruments_router, "validate_and_upsert_ticker", _fake_upsert)
    monkeypatch.setattr(instruments_router, "register_ticker", lambda *a, **k: None)
    monkeypatch.setattr(instruments_router, "run_fundamentals_pipeline", lambda *a, **k: None)
    # Step Functions unconfigured -> in-process path (the stubbed no-ops above).
    monkeypatch.setattr(instruments_router.settings, "prices_state_machine_arn", None)
    monkeypatch.setattr(instruments_router.settings, "fanout_state_machine_arn", None)


def _create_key(client, label, scopes):
    resp = client.post(
        "/admin/api-keys",
        headers={"X-API-Key": MASTER_KEY},
        json={"label": label, "scopes": scopes},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["key"], body


# --------------------------------------------------------------------------- #


def test_health_ok(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_auth_required_without_key(client):
    assert client.get("/v1/instruments").status_code == 401


def test_admin_endpoints_need_master_key(client):
    # A DB key (even write) must not manage keys.
    write_key, _ = _create_key(client, "writer", "read,write")
    assert client.get("/admin/api-keys", headers={"X-API-Key": write_key}).status_code == 401
    assert client.get("/admin/api-keys", headers={"X-API-Key": MASTER_KEY}).status_code == 200


def test_key_scopes_persist_and_are_returned(client):
    _, body = _create_key(client, "reader", "read")
    assert body["scopes"] == "read"
    _, body2 = _create_key(client, "rw", "write,read")
    # normalize_scopes canonicalizes order.
    assert body2["scopes"] == "read,write"


def test_invalid_scope_rejected(client):
    resp = client.post(
        "/admin/api-keys",
        headers={"X-API-Key": MASTER_KEY},
        json={"label": "bad", "scopes": "read,delete"},
    )
    assert resp.status_code == 422


def test_read_key_can_read_but_not_write(client):
    read_key, _ = _create_key(client, "read-only", "read")

    assert client.get("/v1/instruments", headers={"X-API-Key": read_key}).status_code == 200
    # write-gated routes -> 403 for a read-only key
    assert (
        client.post("/v1/instruments", headers={"X-API-Key": read_key}, json={"ticker": "AAPL"}).status_code
        == 403
    )
    assert (
        client.post("/v1/instruments/AAPL/refresh", headers={"X-API-Key": read_key}, json={}).status_code
        == 403
    )


def test_write_key_can_register(client):
    write_key, _ = _create_key(client, "registrar", "read,write")
    resp = client.post("/v1/instruments", headers={"X-API-Key": write_key}, json={"ticker": "msft"})
    assert resp.status_code == 202, resp.text
    assert resp.json()["ticker"] == "MSFT"


def test_runs_endpoint_reads_real_rows(client):
    # Write a real ingestion_runs row via the CRUD, then read it over HTTP.
    from src.core.database import SessionLocal
    from src.data.crud.ingestion_run import finish_run, start_run

    with SessionLocal() as s:
        run_id = start_run(s, dataset="prices_1d", run_date=date.today())
        finish_run(s, run_id, status="success", items_total=5, items_success=5)

    read_key, _ = _create_key(client, "runs-reader", "read")

    listed = client.get("/v1/runs", headers={"X-API-Key": read_key})
    assert listed.status_code == 200
    assert int(listed.headers["X-Total-Count"]) >= 1
    assert any(r["run_id"] == run_id for r in listed.json())

    one = client.get(f"/v1/runs/{run_id}", headers={"X-API-Key": read_key})
    assert one.status_code == 200
    assert one.json()["status"] == "success"

    assert client.get("/v1/runs/does-not-exist", headers={"X-API-Key": read_key}).status_code == 404


def test_refresh_idempotence_returns_409_on_second_call(client):
    # Seed a real registered instrument so refresh passes the 404 guard.
    from src.core.database import SessionLocal
    from src.data.crud.universal_instruments import get_or_create_instrument

    with SessionLocal() as s:
        get_or_create_instrument(
            s,
            "TSLA",
            name="Tesla",
            exchange="NMS",
            currency="USD",
            timezone="America/New_York",
            is_active=True,
            is_scheduled=True,
        )

    write_key, _ = _create_key(client, "refresher", "read,write")
    h = {"X-API-Key": write_key}

    first = client.post("/v1/instruments/TSLA/refresh", headers=h, json={"datasets": ["prices"]})
    assert first.status_code == 202, first.text
    assert first.json()["triggered"][0]["dataset"] == "prices"

    # Lock still held -> nothing new to trigger -> 409.
    second = client.post("/v1/instruments/TSLA/refresh", headers=h, json={"datasets": ["prices"]})
    assert second.status_code == 409


def test_write_rate_limit_returns_429(client):
    # Requires RATE_LIMIT_WRITE_PER_MINUTE to be small (e.g. 3) in the env.
    from src.core.config import settings

    limit = settings.rate_limit_write_per_minute
    assert 0 < limit <= 10, "set RATE_LIMIT_WRITE_PER_MINUTE small for this test"

    write_key, _ = _create_key(client, "rate-limited", "read,write")
    h = {"X-API-Key": write_key}

    statuses = []
    for i in range(limit + 2):
        # Unregistered ticker -> handler would 404, but require_write (and thus
        # the rate-limit bucket) runs first, so the cap still trips.
        r = client.post(f"/v1/instruments/RL{i}/refresh", headers=h, json={})
        statuses.append(r.status_code)

    assert 429 in statuses, statuses
    # The first `limit` write calls must not be rate-limited.
    assert 429 not in statuses[:limit]
