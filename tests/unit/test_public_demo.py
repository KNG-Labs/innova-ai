import httpx
import pytest
import ssl
from sqlalchemy.pool import NullPool

from app.db.session import create_engine
from app.di import init_app_state
from main import create_app


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/knowledge/documents"),
        ("POST", "/knowledge/documents"),
        ("PUT", "/knowledge/documents"),
        ("POST", "/knowledge/reindex"),
        ("GET", "/leads"),
        ("POST", "/leads/00000000-0000-0000-0000-000000000000/deliver"),
        ("GET", "/sessions/00000000-0000-0000-0000-000000000000"),
        ("GET", "/sessions/00000000-0000-0000-0000-000000000000/messages"),
    ],
)
async def test_public_demo_has_no_administrative_routes(monkeypatch, method, path):
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.request(method, path)).status_code == 404
        schema = (await client.get("/openapi.json")).json()
        assert set(schema["paths"]) == {"/message"}


async def test_home_opens_existing_chat_and_assets(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/")
        assert response.status_code == 307
        assert response.headers["location"] == "/static/widget-demo.html"
        assert "demo.js" in (await client.get(response.headers["location"])).text
        assert (await client.get("/static/demo.js")).status_code == 200
        assert (await client.get("/static/images/assistant.webp")).status_code == 200


async def test_public_demo_rejects_enabled_delivery(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv("LEAD_DELIVERY_PROVIDER", "webhook")
    with pytest.raises(RuntimeError, match="LEAD_DELIVERY_PROVIDER=disabled"):
        await init_app_state(create_app())


async def test_vercel_uses_null_pool_and_requires_tls(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    url = "postgresql+asyncpg://innova:innova@localhost/innova_ai_test"
    with pytest.raises(RuntimeError, match="TLS"):
        create_engine(url)
    engine = create_engine(url + "?ssl=verify-full")
    assert isinstance(engine.pool, NullPool)
    await engine.dispose()
    monkeypatch.setenv("VERCEL", "0")
    engine = create_engine(url)
    assert not isinstance(engine.pool, NullPool)
    await engine.dispose()


def test_verified_tls_uses_system_certificates(monkeypatch):
    captured = {}

    def capture_engine(url, **options):
        captured.update(url=url, **options)

    monkeypatch.setattr("app.db.session.create_async_engine", capture_engine)
    create_engine(
        "postgresql+asyncpg://unused/innova_ai_test?ssl=verify-full", null_pool=True
    )
    context = captured["connect_args"]["ssl"]
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert "ssl" not in captured["url"].query
    assert captured["poolclass"] is NullPool
