"""Restore an initial private account snapshot from service secrets, never Git."""
import base64
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from filelock import FileLock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_paths import auth_db_path


def restore_account_snapshot(encoded=None, checksum=None, target=None):
    encoded = encoded if encoded is not None else os.getenv("SCORPRED_AUTH_BOOTSTRAP_B64", "")
    checksum = checksum if checksum is not None else os.getenv("SCORPRED_AUTH_BOOTSTRAP_SHA256", "")
    if not encoded:
        return "not_requested"
    target = Path(target or auth_db_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(target) + ".restore.lock", timeout=10):
        if target.exists():
            return "already_exists"
        if len(encoded) > 12_000_000:
            raise ValueError("Account snapshot exceeds size limit")
        data = base64.b64decode(encoded, validate=True)
        if not checksum or hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError("Account snapshot checksum mismatch")
        if not data.startswith(b"SQLite format 3\0"):
            raise ValueError("Account snapshot is not a SQLite database")
        handle, name = tempfile.mkstemp(dir=target.parent, suffix=".sqlite3")
        temporary = Path(name)
        try:
            with os.fdopen(handle, "wb") as output:
                output.write(data)
            with closing(sqlite3.connect(temporary)) as db:
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Account snapshot integrity check failed")
            # Do not replace a database, even if another startup created one.
            os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return "restored"


if __name__ == "__main__":
    print("Account bootstrap:", restore_account_snapshot())
