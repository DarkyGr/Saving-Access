"""
Rate-limit storage (task 34.2): shared Redis counters and the in-memory
fallback when the shared store is unreachable.

The Redis tests run when RATE_LIMIT_STORAGE points to a Redis server (CI);
the outage test needs only the redis client library.
"""

import os

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from app.rate_limit import build_limiter, rate_limit_exceeded_handler

_STORAGE = os.environ.get("RATE_LIMIT_STORAGE", "memory://")
needs_redis = pytest.mark.skipif(
    not _STORAGE.startswith("redis://"), reason="RATE_LIMIT_STORAGE is not a Redis URI"
)


def _worker(storage_uri: str, limit: str = "3/minute", fallback: str = "5/minute") -> TestClient:
    """One API 'process' with its own Limiter instance, like a uvicorn worker."""
    limiter = build_limiter(storage_uri, fallback)
    limiter.enabled = True
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.post("/api/auth/login")
    @limiter.limit(limit)
    def login(request: Request) -> dict:
        return {"ok": True}

    return TestClient(app)


def test_memory_storage_has_no_fallback():
    limiter = build_limiter("memory://")
    assert limiter._in_memory_fallback_enabled is False


def test_unreachable_store_falls_back_to_memory_limit():
    pytest.importorskip("redis")
    client = _worker("redis://127.0.0.1:1/0", limit="2/minute", fallback="4/minute")
    codes = [client.post("/api/auth/login").status_code for _ in range(6)]
    # No 500s: the fallback limit (4/minute) applies while Redis is down.
    assert codes == [200, 200, 200, 200, 429, 429]


@needs_redis
def test_redis_counters_are_shared_between_workers():
    import redis

    redis.Redis.from_url(_STORAGE).flushdb()
    first, second = _worker(_STORAGE), _worker(_STORAGE)
    codes = [
        (first if i % 2 == 0 else second).post("/api/auth/login").status_code for i in range(5)
    ]
    # 3/minute in total, not per worker.
    assert codes == [200, 200, 200, 429, 429]
    # limits stores keys as "LIMITS:LIMITER/..."
    assert redis.Redis.from_url(_STORAGE).keys("LIMITS:*")


# ── Client IP behind IIS on the same machine (task 36) ───────────────────────

from starlette.requests import Request as StarletteRequest  # noqa: E402

from app.rate_limit import client_ip, user_or_ip_key  # noqa: E402


def _request(peer: str, headers: dict[str, str] | None = None) -> StarletteRequest:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return StarletteRequest({"type": "http", "client": (peer, 50000), "headers": raw})


@pytest.mark.parametrize("loopback", ["127.0.0.1", "::1"])
def test_client_ip_header_trusted_from_local_proxy(monkeypatch, loopback):
    monkeypatch.setenv("CLIENT_IP_HEADER", "X-Client-IP")
    request = _request(loopback, {"X-Client-IP": "192.168.1.40"})
    assert client_ip(request) == "192.168.1.40"
    assert user_or_ip_key(request) == "ip:192.168.1.40"


def test_client_ip_header_ignored_from_remote_peer(monkeypatch):
    monkeypatch.setenv("CLIENT_IP_HEADER", "X-Client-IP")
    # Spoofing attempt: the request did not come through the local proxy.
    assert client_ip(_request("203.0.113.7", {"X-Client-IP": "1.2.3.4"})) == "203.0.113.7"


def test_client_ip_without_setting_or_header(monkeypatch):
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    assert client_ip(_request("127.0.0.1", {"X-Client-IP": "1.2.3.4"})) == "127.0.0.1"
    monkeypatch.setenv("CLIENT_IP_HEADER", "X-Client-IP")
    assert client_ip(_request("127.0.0.1")) == "127.0.0.1"


def test_each_device_gets_its_own_login_limit(monkeypatch):
    monkeypatch.setenv("CLIENT_IP_HEADER", "X-Client-IP")
    app = _worker("memory://", limit="2/minute").app
    # Every request arrives from IIS on this machine, like the installed app.
    client = TestClient(app, client=("127.0.0.1", 50000))
    phone = {"X-Client-IP": "192.168.1.40"}
    laptop = {"X-Client-IP": "192.168.1.50"}
    codes = [client.post("/api/auth/login", headers=h).status_code for h in (phone, phone, phone, laptop)]
    assert codes == [200, 200, 429, 200]
