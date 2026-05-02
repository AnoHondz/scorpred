"""Background scheduler for proactive data refresh.

Replaces the crude threading.Timer loop previously used in app.py.
"""
import logging

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

_log = logging.getLogger("scheduler")
_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            executors={"default": ThreadPoolExecutor(4)},
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 120,
            },
        )
    return _scheduler


def start(app, prediction_service, ac, nba_live_client, monitor) -> BackgroundScheduler:
    """Register all refresh jobs and start the scheduler."""
    from league_config import SUPPORTED_LEAGUE_IDS, CURRENT_SEASON

    sched = get_scheduler()

    @sched.scheduled_job("interval", minutes=25, id="soccer_fixtures")
    def refresh_soccer():
        with app.app_context():
            try:
                for league_id in SUPPORTED_LEAGUE_IDS:
                    ac.get_upcoming_fixtures(league_id, CURRENT_SEASON, next_n=50)
                _log.info("soccer_fixtures refresh done leagues=%s", SUPPORTED_LEAGUE_IDS)
                monitor.record_success("soccer_fixtures")
            except Exception as exc:
                _log.warning("soccer_fixtures refresh failed: %s", exc)
                monitor.record_failure("soccer_fixtures", exc)

    @sched.scheduled_job("interval", minutes=25, start_date="2000-01-01 00:02:00", id="nba_games")
    def refresh_nba():
        with app.app_context():
            try:
                if nba_live_client is not None:
                    nba_live_client.get_upcoming_games(30, 7, "api")
                    _log.info("nba_games refresh done")
                    monitor.record_success("nba_games")
            except Exception as exc:
                _log.warning("nba_games refresh failed: %s", exc)
                monitor.record_failure("nba_games", exc)

    @sched.scheduled_job("interval", minutes=60, id="ml_predictions")
    def refresh_predictions():
        with app.app_context():
            try:
                from services.match_brain import _MATCH_BRAIN
                if _MATCH_BRAIN:
                    for league_id in SUPPORTED_LEAGUE_IDS:
                        _MATCH_BRAIN.refresh_cycle(league_id, min_interval_seconds=0)
                    _log.info("ml_predictions refresh done")
                monitor.record_success("ml_predictions")
            except Exception as exc:
                _log.warning("ml_predictions refresh failed: %s", exc)
                monitor.record_failure("ml_predictions", exc)

    @sched.scheduled_job("interval", minutes=10, id="staleness_check")
    def check_staleness():
        with app.app_context():
            monitor.check_staleness()

    sched.start()
    _log.info("APScheduler started with jobs: soccer_fixtures, nba_games, ml_predictions, staleness_check")
    return sched
