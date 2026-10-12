from pathlib import Path

from app import db


def test_migrations_apply_once(conn) -> None:  # type: ignore[no-untyped-def]
    assert db.migrate(conn) == []
    names = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}
    assert "0001_init.sql" in names
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "businesses", "jobs", "llm_cache", "llm_calls"} <= tables


def test_migrations_run_in_order(tmp_path: Path) -> None:
    (tmp_path / "0002_b.sql").write_text("INSERT INTO t VALUES (2);")
    (tmp_path / "0001_a.sql").write_text("CREATE TABLE t (n INTEGER);INSERT INTO t VALUES (1);")
    c = db.connect(":memory:")
    assert db.migrate(c, tmp_path) == ["0001_a.sql", "0002_b.sql"]
    assert [r["n"] for r in c.execute("SELECT n FROM t ORDER BY rowid")] == [1, 2]


def test_wal_mode_on_file_db(tmp_path: Path) -> None:
    c = db.connect(str(tmp_path / "k.db"))
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_sqlite_vec_loads() -> None:
    c = db.connect(":memory:")
    assert c.execute("SELECT vec_version()").fetchone()[0]
