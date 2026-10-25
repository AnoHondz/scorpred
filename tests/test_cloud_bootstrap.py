import base64
import hashlib
import sqlite3

import pytest

from scripts.cloud_bootstrap import restore_account_snapshot


def test_account_restore_preserves_existing_database(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE example (id INTEGER)")
        db.execute("INSERT INTO example VALUES (7)")
    raw = source.read_bytes()
    target = tmp_path / "cloud" / "auth.db"
    assert restore_account_snapshot(base64.b64encode(raw).decode(), hashlib.sha256(raw).hexdigest(), target) == "restored"
    assert target.read_bytes() == raw
    assert restore_account_snapshot("invalid", "invalid", target) == "already_exists"
    assert target.read_bytes() == raw


def test_invalid_account_snapshot_does_not_create_database(tmp_path):
    target = tmp_path / "auth.db"
    with pytest.raises(ValueError):
        restore_account_snapshot(base64.b64encode(b"not a database").decode(), "wrong", target)
    assert not target.exists()
