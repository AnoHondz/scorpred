"""Thread-safe pipeline health monitor with email alert integration."""
import threading
from datetime import datetime, timedelta, timezone


class PipelineMonitor:
    STALE_THRESHOLDS: dict[str, timedelta] = {
        "soccer_fixtures": timedelta(hours=2),
        "nba_games":       timedelta(hours=2),
        "ml_predictions":  timedelta(hours=3),
    }
    FAILURE_ALERT_THRESHOLD = 3

    def __init__(self, alerter=None):
        self._lock = threading.Lock()
        self._last_success: dict[str, datetime] = {}
        self._consecutive_failures: dict[str, int] = {}
        self._total_failures: dict[str, int] = {}
        self._alerter = alerter

    def record_success(self, pipeline: str) -> None:
        with self._lock:
            self._last_success[pipeline] = datetime.now(timezone.utc)
            self._consecutive_failures[pipeline] = 0

    def record_failure(self, pipeline: str, exc: Exception) -> None:
        with self._lock:
            self._consecutive_failures[pipeline] = (
                self._consecutive_failures.get(pipeline, 0) + 1
            )
            self._total_failures[pipeline] = (
                self._total_failures.get(pipeline, 0) + 1
            )
            consecutive = self._consecutive_failures[pipeline]

        if consecutive >= self.FAILURE_ALERT_THRESHOLD and self._alerter:
            self._alerter.send_alert(
                subject=f"[ScorPred] Pipeline FAILURE: {pipeline}",
                body=(
                    f"Pipeline '{pipeline}' has failed {consecutive} times in a row.\n\n"
                    f"Error: {exc}"
                ),
                severity="error",
                rate_key=f"failure:{pipeline}",
            )

    def check_staleness(self) -> None:
        now = datetime.now(timezone.utc)
        for pipeline, threshold in self.STALE_THRESHOLDS.items():
            with self._lock:
                last = self._last_success.get(pipeline)
            if last is None:
                continue
            age = now - last
            if age > threshold and self._alerter:
                self._alerter.send_alert(
                    subject=f"[ScorPred] Pipeline STALE: {pipeline}",
                    body=(
                        f"Pipeline '{pipeline}' last succeeded "
                        f"{int(age.total_seconds() / 60)} min ago "
                        f"(threshold: {int(threshold.total_seconds() / 60)} min)."
                    ),
                    severity="warning",
                    rate_key=f"stale:{pipeline}",
                )

    def get_status(self) -> dict:
        now = datetime.now(timezone.utc)
        pipelines: dict[str, dict] = {}
        for name in self.STALE_THRESHOLDS:
            with self._lock:
                last = self._last_success.get(name)
                failures = self._consecutive_failures.get(name, 0)
            if last is None:
                status = "unknown"
                age_mins = None
            else:
                age = now - last
                age_mins = int(age.total_seconds() / 60)
                status = "ok" if age < self.STALE_THRESHOLDS[name] else "stale"
            if failures >= self.FAILURE_ALERT_THRESHOLD:
                status = "down"
            pipelines[name] = {
                "status": status,
                "last_success_mins_ago": age_mins,
                "consecutive_failures": failures,
            }
        overall = "ok"
        if any(p["status"] == "down" for p in pipelines.values()):
            overall = "down"
        elif any(p["status"] in ("stale", "unknown") for p in pipelines.values()):
            overall = "degraded"
        return {"overall": overall, "pipelines": pipelines}
