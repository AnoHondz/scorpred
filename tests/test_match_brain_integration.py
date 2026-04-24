from __future__ import annotations

from services.decision_engine import DecisionEngine
from services.match_brain import MatchBrain


def _fixture(fid: int, *, confidence: int, prob_a: float = 60.0, odds_home: float | None = 1.90, status_short: str = "NS"):
    return {
        "fixture": {"id": fid, "date": "2026-04-24T15:00:00+00:00", "status": {"short": status_short}},
        "teams": {
            "home": {"id": 1, "name": f"Home{fid}", "logo": ""},
            "away": {"id": 2, "name": f"Away{fid}", "logo": ""},
        },
        "league": {"name": "Premier League"},
        "prediction": {
            "win_probabilities": {"a": prob_a, "draw": (100 - prob_a) / 2, "b": (100 - prob_a) / 2},
            "best_pick": {"prediction": f"Home{fid}", "reasoning": "Form"},
            "confidence_pct": confidence,
            "data_completeness": {"tier": "strong"},
        },
        "odds": {"home": odds_home} if odds_home is not None else None,
    }


def _make_brain(fixtures):
    index = {str(f["fixture"]["id"]): f for f in fixtures}

    def load_fixtures(_league_id):
        return list(fixtures), None, "test", ""

    def get_fixture_by_id(match_id):
        return index.get(str(match_id))

    return MatchBrain(
        load_fixtures=load_fixtures,
        get_fixture_by_id=get_fixture_by_id,
        decision_engine=DecisionEngine(),
    )


def test_match_analysis_is_cached_per_match_id():
    brain = _make_brain([_fixture(1, confidence=70)])
    first = brain.get_match_analysis(1)
    second = brain.get_match_analysis(1)
    assert first is second  # cached object identity → page consistency guarantee


def test_cache_invalidates_when_status_changes():
    fixture = _fixture(1, confidence=70, status_short="NS")
    brain = _make_brain([fixture])
    scheduled = brain.get_match_analysis(1)
    assert scheduled["status"] == "scheduled"

    # Simulate match completing upstream.
    fixture["fixture"]["status"]["short"] = "FT"
    completed = brain.get_match_analysis(1)
    assert completed["status"] == "completed"
    assert completed is not scheduled


def test_insights_ranks_by_priority_score_not_raw_confidence():
    # Match A: confidence 68 and positive-EV odds → higher priority
    # Match B: confidence 72 but long-odds with negative edge → lower priority
    bet_a = _fixture(1, confidence=68, prob_a=68.0, odds_home=1.85)
    bet_b = _fixture(2, confidence=72, prob_a=72.0, odds_home=1.30)
    brain = _make_brain([bet_b, bet_a])
    insights = brain.get_insights(39)
    ordering = [row["match_id"] for row in insights["top_opportunities"]]
    assert ordering[0] == "1"  # the +EV match leads despite lower confidence


def test_decision_engine_includes_priority_score():
    decision = DecisionEngine().build_decision(
        {
            "home_name": "Arsenal",
            "away_name": "Chelsea",
            "probabilities": {"home": 69, "draw": 16, "away": 15},
            "confidence": 69,
            "data_quality": "Strong Data",
            "odds": {"home": 1.90},
            "metric_breakdown": {"form": {"home": 60, "away": 40}},
        }
    )
    assert "priority_score" in decision
    assert decision["priority_score"] > 0


def test_system_health_check_flags_duplicates_and_missing_results(tmp_path, monkeypatch):
    tracked = [
        {"fixture_id": "1", "status": "completed", "confidence_pct": 70, "is_correct": True},
        {"fixture_id": "1", "status": "completed", "confidence_pct": 70, "is_correct": True},
        {"fixture_id": "2", "status": "completed", "confidence_pct": 65, "is_correct": None},
        {"fixture_id": "3", "status": "open", "confidence_pct": 200, "is_correct": None},
    ]

    def load_fixtures(_league_id):
        return [], None, "test", ""

    def get_fixture_by_id(_match_id):
        return None

    brain = MatchBrain(
        load_fixtures=load_fixtures,
        get_fixture_by_id=get_fixture_by_id,
        decision_engine=DecisionEngine(),
        tracker_recent=lambda limit: tracked[:limit],
    )
    report = brain.system_health_check()
    assert any(entry["fixture_id"] == "1" for entry in report["duplicate_tracking"])
    assert any(entry["fixture_id"] == "2" for entry in report["missing_results"])
    assert any(entry["fixture_id"] == "3" for entry in report["invalid_data"])
    assert report["healthy"] is False


def test_system_health_check_reports_healthy_when_clean():
    brain = MatchBrain(
        load_fixtures=lambda _: ([], None, "test", ""),
        get_fixture_by_id=lambda _: None,
        decision_engine=DecisionEngine(),
        tracker_recent=lambda limit: [
            {"fixture_id": "1", "status": "completed", "confidence_pct": 70, "is_correct": True},
            {"fixture_id": "2", "status": "completed", "confidence_pct": 65, "is_correct": False},
        ],
    )
    report = brain.system_health_check()
    assert report["healthy"] is True


def test_risk_downgrade_blocks_bet_on_high_risk():
    # Confidence modest plus every penalty triggers (limited data, low edge,
    # missing breakdown, live status). risk_score = 35 + 10*4 = 75 > 70.
    decision = DecisionEngine().build_decision(
        {
            "home_name": "Arsenal",
            "away_name": "Chelsea",
            "probabilities": {"home": 65, "draw": 20, "away": 15},
            "confidence": 65,
            "data_quality": "Limited Data",
            "odds": {"home": 1.65},  # implied ~0.606, edge ~0.044 (<0.05)
            "metric_breakdown": None,
            "status": "live",
        }
    )
    assert decision["risk_score"] > 70
    assert decision["action"] in {"CONSIDER", "SKIP"}
