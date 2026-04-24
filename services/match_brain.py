from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable

from services.decision_engine import DecisionEngine


_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MatchBrain:
    """Orchestrates fixture ingestion, canonical decisions, tracking, and insights.

    MatchBrain is the single consumer of DecisionEngine. All pages must obtain
    canonical analysis via :meth:`get_match_analysis` — no page may recompute
    predictions. Canonical outputs are cached per ``match_id`` so the same
    fixture is guaranteed to render identically everywhere.
    """

    load_fixtures: Callable[[int], tuple[list[dict[str, Any]], Any, str, str]]
    get_fixture_by_id: Callable[[str], dict[str, Any] | None]
    decision_engine: DecisionEngine
    tracker_save: Callable[..., str] | None = None
    tracker_recent: Callable[[int], list[dict[str, Any]]] | None = None
    refresh_results: Callable[[], Any] | None = None
    _fixture_index: dict[str, dict[str, Any]] = field(default_factory=dict)
    _status_memory: dict[str, str] = field(default_factory=dict)
    _analysis_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    _health_log: list[str] = field(default_factory=list)

    def get_match_status(self, fixture: dict[str, Any]) -> str:
        status = ((fixture.get("fixture") or {}).get("status") or {}).get("short")
        text = str(status or "").upper()
        if text in {"FT", "AET", "PEN"}:
            return "completed"
        if text in {"PST", "CANC", "ABD", "INT"}:
            return "postponed"
        if text in {"1H", "2H", "HT", "LIVE", "ET", "BT"}:
            return "live"
        return "scheduled"

    def get_date_bucket(self, fixture: dict[str, Any], now_utc: datetime | None = None) -> str:
        now = now_utc or datetime.now(timezone.utc)
        kickoff = self._parse_kickoff((fixture.get("fixture") or {}).get("date"))
        if kickoff is None:
            return "upcoming"
        delta = (kickoff.date() - now.date()).days
        if delta == 0:
            return "today"
        if delta == 1:
            return "tomorrow"
        if delta == -1:
            return "yesterday"
        if delta > 1:
            return "upcoming"
        return "past"

    def canonical_from_fixture(self, fixture: dict[str, Any]) -> dict[str, Any] | None:
        teams = fixture.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        home_name = home.get("name")
        away_name = away.get("name")
        fixture_id = (fixture.get("fixture") or {}).get("id")
        if fixture_id is None or not home_name or not away_name:
            return None

        match_key = str(fixture_id)
        self._fixture_index[match_key] = fixture

        status = self.get_match_status(fixture)
        cached = self._analysis_cache.get(match_key)
        # Reuse the cached canonical object unless the match status moved on
        # (e.g. scheduled → live → completed), so every page renders the same
        # decision for a given match_id.
        if cached is not None and cached.get("status") == status:
            return cached

        raw_probs = (fixture.get("prediction") or {}).get("win_probabilities") or {}
        best_pick = (fixture.get("prediction") or {}).get("best_pick") or {}
        model_conf = (fixture.get("prediction") or {}).get("confidence_pct")
        odds_block = fixture.get("odds") if isinstance(fixture.get("odds"), dict) else None

        decision_input: dict[str, Any] = {
            "home_name": home_name,
            "away_name": away_name,
            "probabilities": {
                "home": raw_probs.get("a"),
                "draw": raw_probs.get("draw"),
                "away": raw_probs.get("b"),
            },
            "confidence": model_conf,
            "recommended_side": best_pick.get("prediction") or best_pick.get("team") or home_name,
            "data_completeness": (fixture.get("prediction") or {}).get("data_completeness") or {"tier": "partial"},
            "strengths": [best_pick.get("reasoning")] if best_pick.get("reasoning") else [],
            "risks": [],
            "status": status,
        }
        if odds_block:
            decision_input["odds"] = odds_block
        decision = self.decision_engine.build_decision(decision_input)

        kickoff = (fixture.get("fixture") or {}).get("date") or ""
        league = (fixture.get("league") or {}).get("name") or "Soccer"
        canonical = {
            "match_id": match_key,
            "matchup": f"{home_name} vs {away_name}",
            "league": league,
            "kickoff": kickoff,
            "status": status,
            "prediction": decision,
            "teams": {
                "home": home,
                "away": away,
            },
            "date_bucket": self.get_date_bucket(fixture),
        }
        self._analysis_cache[match_key] = canonical
        return canonical

    def get_match_analysis(self, match_id: str | int) -> dict[str, Any] | None:
        match_key = str(match_id)
        fixture = self._fixture_index.get(match_key) or self.get_fixture_by_id(match_key)
        if not fixture:
            return None
        return self.canonical_from_fixture(fixture)

    def invalidate_cache(self, match_id: str | int | None = None) -> None:
        """Drop cached canonical analyses. Called when upstream data changes."""
        if match_id is None:
            self._analysis_cache.clear()
            return
        self._analysis_cache.pop(str(match_id), None)

    @staticmethod
    def _opportunity_priority(row: dict[str, Any]) -> float:
        pred = row.get("prediction") or {}
        explicit = pred.get("priority_score")
        if isinstance(explicit, (int, float)):
            return float(explicit)
        # Fallback when an older DecisionEngine output is cached.
        edge = pred.get("edge_score")
        ev = pred.get("expected_value")
        dq = float(pred.get("data_quality") or 0) / 100.0
        if edge is None and ev is None:
            conf = float(pred.get("confidence") or 0) / 100.0
            return conf * 0.7 + dq * 0.3
        return max(0.0, edge or 0.0) * 0.5 + max(0.0, ev or 0.0) * 0.3 + dq * 0.2

    def get_insights(self, league_id: int) -> dict[str, Any]:
        fixtures, *_ = self.load_fixtures(league_id)
        canonical = [self.canonical_from_fixture(f) for f in fixtures or []]
        canonical = [row for row in canonical if row]
        # Rank by the canonical priority_score (edge + EV + data quality),
        # breaking ties on raw confidence for stability.
        opportunities = sorted(
            canonical,
            key=lambda row: (
                -self._opportunity_priority(row),
                -int((row["prediction"] or {}).get("confidence") or 0),
            ),
        )
        high_conf = [row for row in opportunities if int((row["prediction"] or {}).get("confidence") or 0) >= 64]
        return {
            "top_opportunities": opportunities[:6],
            "high_confidence": high_conf[:6],
        }

    def track_match(self, canonical_match: dict[str, Any]) -> str:
        if not self.tracker_save:
            return ""
        prediction = canonical_match.get("prediction") or {}
        teams = canonical_match.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        probs = prediction.get("probabilities") or {}
        return self.tracker_save(
            sport="soccer",
            team_a=home.get("name") or "Home",
            team_b=away.get("name") or "Away",
            predicted_winner=prediction.get("side") or home.get("name") or "Home",
            win_probs={
                "a": probs.get("home") or 0,
                "draw": probs.get("draw") or 0,
                "b": probs.get("away") or 0,
            },
            confidence="High" if (prediction.get("confidence") or 0) >= 66 else "Medium" if (prediction.get("confidence") or 0) >= 55 else "Low",
            game_date=(canonical_match.get("kickoff") or "")[:10],
            team_a_id=home.get("id"),
            team_b_id=away.get("id"),
            league_name=canonical_match.get("league"),
            fixture_id=canonical_match.get("match_id"),
        )

    def refresh_tracked_matches(self) -> list[dict[str, Any]]:
        if self.refresh_results:
            try:
                self.refresh_results()
            except Exception:
                pass
        if not self.tracker_recent:
            return []
        tracked = self.tracker_recent(300) or []
        rows: list[dict[str, Any]] = []
        for row in tracked:
            fixture_id = str(row.get("fixture_id") or "")
            status = "completed" if str(row.get("status") or "").lower() == "completed" else "open"
            rows.append({**row, "match_id": fixture_id, "tracking_status": status})
        return rows

    def get_performance_snapshot(self, completed: list[dict[str, Any]]) -> dict[str, Any]:
        wins = sum(1 for row in completed if row.get("is_correct") is True)
        losses = sum(1 for row in completed if row.get("is_correct") is False)
        pushes = max(0, len(completed) - wins - losses)
        if not completed:
            return {"win_rate": "N/A", "roi": "N/A", "record": "0W-0L-0P"}
        win_rate = round((wins / len(completed)) * 100, 1)
        return {
            "win_rate": f"{win_rate:.1f}%",
            "roi": "N/A",
            "record": f"{wins}W-{losses}L-{pushes}P",
        }

    def get_alerts(self, league_id: int) -> list[dict[str, Any]]:
        fixtures, *_ = self.load_fixtures(league_id)
        alerts: list[dict[str, Any]] = []
        for canonical in [self.canonical_from_fixture(item) for item in fixtures or []]:
            if not canonical:
                continue
            prediction = canonical.get("prediction") or {}
            confidence = int(prediction.get("confidence") or 0)
            if confidence >= 70 and prediction.get("action") == "BET":
                alerts.append(
                    {
                        "type": "high_confidence_opportunity",
                        "title": canonical.get("matchup"),
                        "description": f"{prediction.get('side')} at {confidence}% confidence",
                        "match_id": canonical.get("match_id"),
                    }
                )
            last = self._status_memory.get(canonical["match_id"])
            current = canonical.get("status")
            if last and current != last:
                alerts.append(
                    {
                        "type": "status_change",
                        "title": canonical.get("matchup"),
                        "description": f"Status changed from {last} to {current}",
                        "match_id": canonical.get("match_id"),
                    }
                )
            self._status_memory[canonical["match_id"]] = current
        return alerts[:20]

    def system_health_check(self) -> dict[str, Any]:
        """Watchdog that inspects the current tracked store for integrity.

        Returns a structured report — never raises — so it can be called on
        every page load without crashing the request.
        """
        report: dict[str, Any] = {
            "consistency": [],
            "invalid_data": [],
            "missing_results": [],
            "duplicate_tracking": [],
        }

        tracked: list[dict[str, Any]] = []
        if self.tracker_recent:
            try:
                tracked = list(self.tracker_recent(500) or [])
            except Exception as exc:  # pragma: no cover - defensive
                _logger.warning("tracker_recent failed during health check: %s", exc)
                tracked = []

        seen_ids: dict[str, int] = {}
        for row in tracked:
            fixture_id = str(row.get("fixture_id") or "").strip()
            if fixture_id:
                seen_ids[fixture_id] = seen_ids.get(fixture_id, 0) + 1

            status = str(row.get("status") or "").strip().lower()
            confidence = row.get("confidence_pct")
            if confidence is not None:
                try:
                    conf_val = float(confidence)
                    if conf_val < 0 or conf_val > 100:
                        report["invalid_data"].append(
                            {"fixture_id": fixture_id, "reason": "confidence out of range"}
                        )
                except (TypeError, ValueError):
                    report["invalid_data"].append(
                        {"fixture_id": fixture_id, "reason": "confidence not numeric"}
                    )
            if status == "completed" and row.get("is_correct") is None:
                report["missing_results"].append(
                    {"fixture_id": fixture_id, "reason": "completed but result unresolved"}
                )

        for fixture_id, count in seen_ids.items():
            if count > 1:
                report["duplicate_tracking"].append(
                    {"fixture_id": fixture_id, "count": count}
                )

        # Consistency: any cached canonical whose underlying fixture has moved on.
        for match_key, canonical in list(self._analysis_cache.items()):
            fixture = self._fixture_index.get(match_key)
            if not fixture:
                continue
            live_status = self.get_match_status(fixture)
            if live_status != canonical.get("status"):
                report["consistency"].append(
                    {
                        "match_id": match_key,
                        "cached_status": canonical.get("status"),
                        "live_status": live_status,
                    }
                )
                # Self-heal by dropping the stale cache entry so next access recomputes.
                self._analysis_cache.pop(match_key, None)

        healthy = not any(report[bucket] for bucket in report)
        report["healthy"] = healthy
        self._health_log.append(
            "healthy" if healthy else "issues:" + ",".join(k for k, v in report.items() if v and k != "healthy")
        )
        if len(self._health_log) > 50:
            self._health_log = self._health_log[-50:]
        return report

    @staticmethod
    def _parse_kickoff(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
