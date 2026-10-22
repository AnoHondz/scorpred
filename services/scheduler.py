"""Background scheduler for proactive data refresh.

Replaces the crude threading.Timer loop previously used in app.py.
"""
import logging

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

from services.pipeline_monitor import combine_refresh_outcomes, fixture_refresh_outcome

_log = logging.getLogger("scheduler")
_scheduler: BackgroundScheduler | None = None


def _record_refresh(monitor, pipeline: str, outcomes: list[dict]) -> None:
    outcome = combine_refresh_outcomes(outcomes)
    if outcome["status"] == "success":
        monitor.record_success(pipeline, observed_at=outcome["observed_at"])
        _log.info("%s refresh succeeded observed_at=%s", pipeline, outcome["observed_at"])
    else:
        error = RuntimeError(outcome["error"] or "Refresh did not complete successfully")
        monitor.record_failure(pipeline, error)
        _log.warning("%s refresh %s: %s", pipeline, outcome["status"], error)


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


def start(app, prediction_service, ac, nba_live_client, monitor, *, match_brain) -> BackgroundScheduler:
    """Register all refresh jobs and start the scheduler."""
    from league_config import SUPPORTED_LEAGUE_IDS

    sched = get_scheduler()
    if sched.running:
        return sched

    @sched.scheduled_job("interval", minutes=25, id="soccer_fixtures")
    def refresh_soccer():
        with app.app_context():
            outcomes = []
            for league_id in SUPPORTED_LEAGUE_IDS:
                try:
                    _cards, fixtures, error, source, marker = prediction_service.get_fixture_cards(league_id)
                    outcome = fixture_refresh_outcome(fixtures, error, source, marker)
                    if outcome.get("error"):
                        outcome["error"] = f"League {league_id}: {outcome['error']}"
                    outcomes.append(outcome)
                except Exception as exc:
                    outcomes.append({"status": "failed", "observed_at": None, "error": f"League {league_id}: {exc}"})
            _record_refresh(monitor, "soccer_fixtures", outcomes)

    @sched.scheduled_job("interval", minutes=25, start_date="2000-01-01 00:02:00", id="nba_games")
    def refresh_nba():
        with app.app_context():
            try:
                if nba_live_client is None:
                    raise RuntimeError("NBA provider is unavailable")
                nba_live_client.get_upcoming_games(30, 7, "api")
                # [] can mean a valid off-season schedule. The source outcome decides health.
                outcome = nba_live_client.get_schedule_refresh_status()
                _record_refresh(monitor, "nba_games", [outcome])
            except Exception as exc:
                _log.warning("nba_games refresh failed: %s", exc)
                monitor.record_failure("nba_games", exc)

    @sched.scheduled_job("interval", minutes=60, id="ml_predictions")
    def refresh_predictions():
        with app.app_context():
            outcomes = []
            for league_id in SUPPORTED_LEAGUE_IDS:
                try:
                    if match_brain is None:
                        raise RuntimeError("Prediction brain is unavailable")
                    outcome = match_brain.refresh_cycle(league_id, min_interval_seconds=0)
                    if isinstance(outcome, dict):
                        outcome = dict(outcome)
                        if outcome.get("error"):
                            outcome["error"] = f"League {league_id}: {outcome['error']}"
                    outcomes.append(outcome)
                except Exception as exc:
                    outcomes.append({"status": "failed", "observed_at": None, "error": f"League {league_id}: {exc}"})
            _record_refresh(monitor, "ml_predictions", outcomes)

    @sched.scheduled_job("interval", minutes=10, id="staleness_check")
    def check_staleness():
        with app.app_context():
            monitor.check_staleness()

    @sched.scheduled_job("interval", hours=6, start_date="2000-01-01 00:05:00", id="cache_prune")
    def prune_cache():
        from services import cache_pruner
        try:
            cache_pruner.prune()
        except Exception as exc:
            _log.warning("cache_prune failed: %s", exc)

    sched.start()
    _log.info("APScheduler started with jobs: soccer_fixtures, nba_games, ml_predictions, staleness_check, cache_prune")
    return sched


def stop():
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
