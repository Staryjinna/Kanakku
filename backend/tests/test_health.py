from fastapi.testclient import TestClient

from app.llm.providers.fake import FakeProvider


def test_health_ok(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "db": "ok", "ollama": "ok"}


def test_health_reports_ollama_down(client: TestClient, provider: FakeProvider) -> None:
    provider.up = False
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["ollama"] == "unreachable"


def test_serves_frontend_with_spa_fallback(tmp_path, settings, provider) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient as TC

    from app.main import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "a.js").write_text("1")
    settings.frontend_dist = str(dist)
    with TC(create_app(settings, provider)) as c:
        assert "app" in c.get("/dashboard").text
        assert c.get("/assets/a.js").text == "1"
        assert c.get("/api/nope").status_code == 404
        assert "app" in c.get("/../../etc/passwd").text  # traversal falls back to index
