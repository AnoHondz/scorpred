"""Loopback-only local backend owner. No training or research activation."""
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from datetime import UTC, datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".tmp/local-app"
SOURCES = ("app.py", "services/prediction_service.py", "services/cache_service.py", "services/nba_matchup_context.py",
           "nba_routes.py", "nba_live_client.py", "services/nba_early_season.py", "nfl_routes.py", "scripts/run_local.py")


def source_fingerprint():
    return hashlib.sha256(b"".join((ROOT / name).read_bytes() for name in SOURCES)).hexdigest()


def main():
    import msvcrt
    STATE.mkdir(parents=True, exist_ok=True)
    # OS releases this lock on exit; stale PID files can never create two owners.
    with (STATE / "backend.lock").open("a+b") as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SystemExit("ScorPred local backend is already owned by another process.")
        os.chdir(ROOT)
        sys.path.insert(0, str(ROOT))
        os.environ.update(PORT="5001", SCORPRED_TESTING="0", SCORPRED_SCHEDULER_ENABLED="1",
                          NFL_ADVANCED_RESEARCH_ENABLED="0", NFL_WINNER_RESEARCH_ENABLED="0", NBA_EARLY_SEASON_RESEARCH_ENABLED="0", ALERT_EMAIL="")
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        import app as application
        from flask import jsonify
        from werkzeug.serving import make_server

        identity = {"app": "ScorPred", "pid": os.getpid(), "root": str(ROOT),
                    "source_fingerprint": source_fingerprint(), "research_enabled": False}
        application.app.add_url_rule("/api/local-runtime", "local_runtime", lambda: jsonify(identity))
        stop = STATE / "backend.stop"
        stop.unlink(missing_ok=True)
        server = make_server("127.0.0.1", 5001, application.app, threaded=True)
        (STATE / "backend.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
        application.start_background_services()
        # Invoke registered jobs once after startup. Their actual receipts, not
        # server startup, determine pipeline health; singleton limits still apply.
        if application._pipeline_scheduler is not None:
            for delay, name in enumerate(("soccer_fixtures", "nba_games", "ml_predictions"), 1):
                application._pipeline_scheduler.modify_job(name, next_run_time=datetime.now(UTC) + timedelta(seconds=delay))

        def wait_for_stop():
            while not stop.exists():
                time.sleep(.5)
            server.shutdown()

        threading.Thread(target=wait_for_stop, daemon=True).start()
        try:
            server.serve_forever()
        finally:
            application.stop_background_services()
            server.server_close()


if __name__ == "__main__":
    main()
