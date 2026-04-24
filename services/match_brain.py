from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from services.decision_engine import DecisionEngine


@dataclass(slots=True)
class MatchBrain:
    """Orchestrates fixture ingestion, canonical decisions, tracking, and insights."""

    load_fixtures: Callable[[int], tuple[list[dict[str, Any]], Any, str, str]]
    get_fixture_by_id: Callable[[str], dict[str, Any] | None]
    decision_engine: DecisionEngine
    tracker_save: Callable[..., str] | None = None
    tracker_recent: Callable[[int], list[dict[str, Any]]] | None = None
    refresh_results: Callable[[], Any] | None = None
    _fixture_index: dict[str, dict[str, Any]] = field(default_factory=dict)
    _analysis_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    _status_memory: dict[str, str] = field(default_factory=dict)

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

        self._fixture_index[str(fixture_id)] = fixture
        raw_probs = (fixture.get("prediction") or {}).get("win_probabilities") or {}
        best_pick = (fixture.get("prediction") or {}).get("best_pick") or {}
        model_conf = (fixture.get("prediction") or {}).get("confidence_pct")

        decision = self.decision_engine.build_decision(
            {
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
            }
        )

        kickoff = (fixture.get("fixture") or {}).get("date") or ""
        status = self.get_match_status(fixture)
        league = (fixture.get("league") or {}).get("name") or "Soccer"
        reason = " | ".join((decision.get("reasoning") or {}).get("strengths", []))
        breakdown = {
            "model_probability": decision.get("model_probability"),
            "implied_probability": decision.get("implied_probability"),
            "edge_score": decision.get("edge_score"),
            "expected_value": decision.get("expected_value"),
            "risk_score": decision.get("risk_score"),
            "risk_level": decision.get("risk_level"),
            "decision_grade": decision.get("decision_grade"),
        }
        canonical = {
            "match_id": str(fixture_id),
            "matchup": f"{home_name} vs {away_name}",
            "league": league,
            "kickoff": kickoff,
            "status": status,
            "recommended_side": decision.get("side"),
            "action": decision.get("action"),
            "confidence": decision.get("confidence"),
            "probabilities": decision.get("probabilities"),
            "data_quality": decision.get("data_quality"),
            "reason": reason,
            "metric_breakdown": breakdown,
            "model_probability": breakdown.get("model_probability"),
            "implied_probability": breakdown.get("implied_probability"),
            "edge_score": breakdown.get("edge_score"),
            "expected_value": breakdown.get("expected_value"),
            "risk_score": breakdown.get("risk_score"),
            "risk_level": breakdown.get("risk_level"),
            "decision_grade": breakdown.get("decision_grade"),
            "prediction": decision,
            "teams": {
                "home": home,
                "away": away,
            },
            "date_bucket": self.get_date_bucket(fixture),
        }
        return canonical

    def get_match_analysis(self, match_id: str | int) -> dict[str, Any] | None:
        match_key = str(match_id)
        cached = self._analysis_cache.get(match_key)
        if cached is not None:
            return cached
        fixture = self._fixture_index.get(match_key) or self.get_fixture_by_id(match_key)
        if not fixture:
            return None
        canonical = self.canonical_from_fixture(fixture)
        if canonical and self._validate_canonical(canonical):
            self._analysis_cache[match_key] = canonical
            return canonical
        return None

    def get_insights(self, league_id: int) -> dict[str, Any]:
        fixtures, *_ = self.load_fixtures(league_id)
        canonical = [self.canonical_from_fixture(f) for f in fixtures or []]
        canonical = [row for row in canonical if row]
        opportunities = sorted(
            canonical,
            key=lambda row: (
                -self._priority_score(row),
                -(row.get("confidence") or 0),
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
        snapshot = {
            "canonical_snapshot": {
                "match_id": canonical_match.get("match_id"),
                "matchup": canonical_match.get("matchup"),
                "sport": "soccer",
                "league": canonical_match.get("league"),
                "kickoff": canonical_match.get("kickoff"),
                "status": canonical_match.get("status"),
                "recommended_side": canonical_match.get("recommended_side"),
                "action": canonical_match.get("action"),
                "confidence": canonical_match.get("confidence"),
                "probabilities": canonical_match.get("probabilities"),
                "data_quality": canonical_match.get("data_quality"),
                "reason": canonical_match.get("reason"),
                "model_probability": (canonical_match.get("metric_breakdown") or {}).get("model_probability"),
                "implied_probability": (canonical_match.get("metric_breakdown") or {}).get("implied_probability"),
                "edge_score": (canonical_match.get("metric_breakdown") or {}).get("edge_score"),
                "expected_value": (canonical_match.get("metric_breakdown") or {}).get("expected_value"),
                "risk_score": (canonical_match.get("metric_breakdown") or {}).get("risk_score"),
                "risk_level": (canonical_match.get("metric_breakdown") or {}).get("risk_level"),
                "decision_grade": (canonical_match.get("metric_breakdown") or {}).get("decision_grade"),
                "tracked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "result": None,
                "evaluation_status": "OPEN",
            }
        }
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
            model_factors=snapshot,
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

    @staticmethod
    def _priority_score(row: dict[str, Any]) -> float:
        confidence = float(row.get("confidence") or 0.0)
        data_quality = float(row.get("data_quality") or 0.0)
        metric = row.get("metric_breakdown") or {}
        edge_score = metric.get("edge_score")
        expected_value = metric.get("expected_value")
        if edge_score is None or expected_value is None:
            return confidence * 0.75 + data_quality * 0.25
        return confidence * 0.45 + float(edge_score) * 100 * 0.30 + float(expected_value) * 100 * 0.15 + data_quality * 0.10

    @staticmethod
    def _validate_canonical(payload: dict[str, Any]) -> bool:
        required = {
            "match_id",
            "matchup",
            "league",
            "kickoff",
            "status",
            "recommended_side",
            "action",
            "confidence",
            "probabilities",
            "data_quality",
            "reason",
            "metric_breakdown",
            "model_probability",
            "implied_probability",
            "edge_score",
            "expected_value",
            "risk_score",
            "risk_level",
            "decision_grade",
        }
        return all(key in payload for key in required)

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
