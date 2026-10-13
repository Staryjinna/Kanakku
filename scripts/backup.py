"""Back up (and restore) the SQLite database using SQLite's online backup API.

  python scripts/backup.py                    # write data/backups/kanakku-<timestamp>.db, keep newest 14
  python scripts/backup.py --restore FILE     # replace the live DB with FILE (stop the app first!)

Safe to run while the app is running. Uploaded bill files live in data/uploads/ and are NOT part of
the database backup: copy that folder too (e.g. `rsync -a data/uploads/ <backup>/uploads/`).
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402

KEEP = 14
PREFIX = "kanakku-"


def backup(db_path: Path, backup_dir: Path, keep: int = KEEP) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    target = backup_dir / f"{PREFIX}{stamp}.db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)  # consistent snapshot, includes WAL contents
    finally:
        dst.close()
        src.close()
    for old in sorted(backup_dir.glob(f"{PREFIX}*.db"))[:-keep]:
        old.unlink()
    return target


def check_backup(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"{path} failed the integrity check")
    finally:
        conn.close()


def restore(backup_file: Path, db_path: Path) -> Path | None:
    """Replace db_path with backup_file. Returns the safety copy of the old DB, if there was one."""
    check_backup(backup_file)
    safety = None
    if db_path.exists():
        safety = db_path.with_name(db_path.name + ".before-restore")
        shutil.copy2(db_path, safety)
    for suffix in ("-wal", "-shm"):  # stale WAL files would be replayed onto the restored DB
        db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
    shutil.copy2(backup_file, db_path)
    return safety


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--restore", metavar="FILE")
    args = parser.parse_args()
    settings = Settings()
    db_path = Path(settings.db_path)
    if args.restore:
        safety = restore(Path(args.restore), db_path)
        print(f"Restored {args.restore} to {db_path}")
        if safety:
            print(f"Previous database kept at {safety}")
        return 0
    target = backup(db_path, Path(settings.backup_dir))
    print(f"Backup written to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
