import importlib.util
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("backup", ROOT / "scripts" / "backup.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_db(path: Path, rows: list[str]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    conn.executemany("INSERT INTO t VALUES (?)", [(r,) for r in rows])
    conn.commit()
    conn.close()


def values(path: Path) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [r[0] for r in conn.execute("SELECT v FROM t ORDER BY rowid")]
    finally:
        conn.close()


def test_backup_then_restore_round_trip(tmp_path: Path) -> None:
    mod = load()
    db = tmp_path / "live.db"
    make_db(db, ["a", "b"])
    snap = mod.backup(db, tmp_path / "backups")
    assert values(snap) == ["a", "b"]
    make_db(db, ["c"])  # data written after the backup
    assert values(db) == ["a", "b", "c"]
    safety = mod.restore(snap, db)
    assert values(db) == ["a", "b"]
    assert values(safety) == ["a", "b", "c"]  # old DB is kept, not destroyed


def test_backup_while_connection_open_includes_wal_data(tmp_path: Path) -> None:
    mod = load()
    db = tmp_path / "live.db"
    make_db(db, ["a"])
    live = sqlite3.connect(db)
    live.execute("INSERT INTO t VALUES ('uncheckpointed')")
    live.commit()
    snap = mod.backup(db, tmp_path / "b")
    live.close()
    assert values(snap) == ["a", "uncheckpointed"]


def test_keeps_only_newest_14(tmp_path: Path) -> None:
    mod = load()
    db = tmp_path / "live.db"
    make_db(db, ["a"])
    made = [mod.backup(db, tmp_path / "b") for _ in range(17)]
    left = sorted((tmp_path / "b").glob("kanakku-*.db"))
    assert len(left) == 14 and left[-1] == made[-1] and made[0] not in left


def test_restore_rejects_corrupt_backup(tmp_path: Path) -> None:
    mod = load()
    db = tmp_path / "live.db"
    make_db(db, ["keep me"])
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a database" * 100)
    with pytest.raises(sqlite3.DatabaseError):
        mod.restore(bad, db)
    assert values(db) == ["keep me"]


def test_restore_removes_stale_wal(tmp_path: Path) -> None:
    mod = load()
    db = tmp_path / "live.db"
    make_db(db, ["a"])
    snap = mod.backup(db, tmp_path / "b")
    (tmp_path / "live.db-wal").write_bytes(b"stale")
    mod.restore(snap, db)
    assert not (tmp_path / "live.db-wal").exists() and values(db) == ["a"]


def test_missing_db(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load().backup(tmp_path / "nope.db", tmp_path / "b")
