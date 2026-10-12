from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.llm.gateway import Gateway
from app.llm.providers.fake import FakeProvider
from app.main import create_app

PASSWORD = "correct-horse-battery"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        env="test",
        db_path=":memory:",
        upload_dir=str(tmp_path / "uploads"),
        worker_enabled=False,
        frontend_dist=str(tmp_path / "no-dist"),
    )


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def conn() -> Iterator[object]:
    c = db.connect(":memory:")
    db.migrate(c)
    yield c
    c.close()


@pytest.fixture
def gateway(conn, settings: Settings, provider: FakeProvider) -> Gateway:  # type: ignore[no-untyped-def]
    return Gateway(provider, conn, settings)


@pytest.fixture
def client(settings: Settings, provider: FakeProvider) -> Iterator[TestClient]:
    with TestClient(create_app(settings, provider, FakeReranker())) as c:
        yield c


def signup_payload(email: str = "a@example.com", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": email,
        "password": PASSWORD,
        "name": "Asha",
        "business_name": "Asha Traders",
        "state_code": "33",
        "consent": True,
    }
    base.update(over)
    return base


@pytest.fixture
def business_id(conn) -> int:  # type: ignore[no-untyped-def]
    from app.auth import service

    uid = service.signup(
        conn, email="u@example.com", password=PASSWORD, name="U", business_name="B", state_code="33"
    )
    return int(
        conn.execute("SELECT id FROM businesses WHERE owner_user_id=?", (uid,)).fetchone()[0]
    )


class FakeReranker:
    """Scores passages by how many query words they contain."""

    async def score(self, query: str, passages: list[str]) -> list[float]:
        words = set(query.lower().split())
        return [float(len(words & set(p.lower().split()))) for p in passages]


@pytest.fixture
def reranker() -> FakeReranker:
    return FakeReranker()
