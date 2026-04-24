from __future__ import annotations

from unittest.mock import patch

import app as flask_app_module
import model_tracker as mt
from services import calibration_service, model_trust_service
from services.decision_engine import DecisionEngine
from services.match_brain import MatchBrain


def _fixture(fid: int = 101, *, with_odds: bool = True):
    odds = {"home": 2.10, "draw": 3.2, "away": 3.6} if with_odds else {}
    return {
        "fixture": {"id": fid, "date": "2026-04-24T15:00:00+00:00", "status": {"short": "NS"}},
        "teams": {
            "home": {"id": 1, "name": "Arsenal", "logo": ""},
            "away": {"id": 2, "name": "Chelsea", "logo": ""},
        },
        "league": {"name": "Premier League"},
        "prediction": {
            "win_probabilities": {"a": 52.0, "draw": 24.0, "b": 24.0},
            "best_pick": {"prediction": "Arsenal", "reasoning": "Stronger recent form"},
            "confidence_pct": 66,
            "data_completeness": {"tier": "strong"},
            "odds": odds,
        },
    }


def _client():
    flask_app_module.app.config["TESTING"] = True
    with flask_app_module.app.test_client() as client:
        return client


def test_decision_engine_contains_required_fields():
    decision = DecisionEngine().build_decision(
        {
            "home_name": "Arsenal",
            "away_name": "Chelsea",
            "probabilities": {"home": 55, "draw": 22, "away": 23},
            "confidence": 68,
            "data_completeness": {"tier": "strong"},
        }
    )
    assert "confidence" in decision
    assert "edge_score" in decision
    assert "risk_level" in decision
    assert "reasoning" in decision
    assert decision["reasoning"]["strengths"]
    assert decision["reasoning"]["risks"]
    assert decision["edge_score"] is None


def test_edge_score_is_decimal_and_formatter_is_percent():
    decision = DecisionEngine().build_decision(
        {
            "home_name": "Arsenal",
            "away_name": "Chelsea",
            "probabilities": {"home": 60, "draw": 20, "away": 20},
            "confidence": 60,
            "odds": {"home": 2.0},
            "data_completeness": {"tier": "strong"},
        }
    )
    assert decision["edge_score"] == 0.1
    assert flask_app_module.format_percent_decimal(decision["edge_score"]) == "+10.0%"


def test_missing_odds_does_not_fake_ev():
    decision = DecisionEngine().build_decision(
        {
            "home_name": "Arsenal",
            "away_name": "Chelsea",
            "probabilities": {"home": 56, "draw": 22, "away": 22},
            "confidence": 58,
            "data_completeness": {"tier": "strong"},
        }
    )
    assert decision["implied_probability"] is None
    assert decision["edge_score"] is None
    assert decision["expected_value"] is None


def test_analyze_match_uses_match_id_and_prediction_route_renders():
    canonical = {
        "match_id": "101",
        "matchup": "Arsenal vs Chelsea",
        "kickoff": "2026-04-24T15:00:00+00:00",
        "prediction": {
            "side": "Arsenal",
            "action": "BET",
            "confidence": 66,
            "probabilities": {"home": 52.0, "draw": 24.0, "away": 24.0},
            "edge_score": 0.05,
            "risk_level": "LOW",
            "expected_value": 0.05,
            "risk_score": 0.12,
            "model_probability": 0.66,
            "implied_probability": 0.61,
            "decision_grade": "A",
            "data_quality": 85,
            "reasoning": {"strengths": ["Stronger recent form"], "risks": ["Late squad news"]},
        },
        "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
    }
    with patch.object(flask_app_module, "_MATCH_BRAIN") as brain:
        brain.get_match_analysis.return_value = canonical
        client = _client()
        rv = client.get("/prediction?match_id=101")
    assert rv.status_code == 200
    assert b"Arsenal" in rv.data
    assert b"66" in rv.data


def test_insights_route_no_redirect_loop():
    with patch.object(flask_app_module, "_MATCH_BRAIN") as brain:
        brain.get_insights.return_value = {"top_opportunities": [], "high_confidence": []}
        client = _client()
        rv = client.get("/insights", follow_redirects=False)
    assert rv.status_code == 200


def test_performance_ignores_open_matches_for_win_rate():
    completed = [{"status": "completed", "is_correct": True, "date": "2026-04-20"}]
    pending = [{"status": "pending", "is_correct": None, "date": "2026-04-20"}]
    with patch.object(mt, "get_completed_predictions", return_value=completed), patch.object(mt, "get_pending_predictions", return_value=pending):
        client = _client()
        rv = client.get("/performance")
    assert rv.status_code == 200
    assert b"100.0%" in rv.data


def test_tracking_deduplicates_and_updates_completion(tmp_path, monkeypatch):
    tracking_file = tmp_path / "tracking.json"
    monkeypatch.setattr(mt, "_TRACKING_FILE", str(tracking_file))
    pred_id_1 = mt.save_prediction(
        sport="soccer",
        team_a="Arsenal",
        team_b="Chelsea",
        predicted_winner="A",
        win_probs={"a": 52, "draw": 24, "b": 24},
        confidence="High",
        game_date="2026-04-24",
        fixture_id="101",
    )
    pred_id_2 = mt.save_prediction(
        sport="soccer",
        team_a="Arsenal",
        team_b="Chelsea",
        predicted_winner="A",
        win_probs={"a": 52, "draw": 24, "b": 24},
        confidence="High",
        game_date="2026-04-24",
        fixture_id="101",
    )
    assert pred_id_1 == pred_id_2
    assert len(mt.get_recent_predictions(10)) == 1

    updated = mt.update_prediction_result(pred_id_1, "A", {"a": 2, "b": 1}, fixture_id="101")
    assert updated is True
    completed = mt.get_completed_predictions(10)
    assert completed
    assert completed[0]["status"] == "completed"


def test_match_brain_returns_same_cached_object():
    fixture = _fixture()
    brain = MatchBrain(
        load_fixtures=lambda _league: ([fixture], None, "configured", ""),
        get_fixture_by_id=lambda _mid: fixture,
        decision_engine=DecisionEngine(),
    )
    first = brain.get_match_analysis("101")
    second = brain.get_match_analysis("101")
    assert first is second


def test_top_opportunities_sort_handles_none_ev():
    with_odds = _fixture(101, with_odds=True)
    without_odds = _fixture(102, with_odds=False)
    brain = MatchBrain(
        load_fixtures=lambda _league: ([with_odds, without_odds], None, "configured", ""),
        get_fixture_by_id=lambda _mid: with_odds,
        decision_engine=DecisionEngine(),
    )
    insights = brain.get_insights(39)
    assert len(insights["top_opportunities"]) == 2


def test_tracking_stores_canonical_snapshot(tmp_path, monkeypatch):
    tracking_file = tmp_path / "tracking.json"
    monkeypatch.setattr(mt, "_TRACKING_FILE", str(tracking_file))
    fixture = _fixture()
    brain = MatchBrain(
        load_fixtures=lambda _league: ([fixture], None, "configured", ""),
        get_fixture_by_id=lambda _mid: fixture,
        decision_engine=DecisionEngine(),
        tracker_save=mt.save_prediction,
    )
    canonical = brain.get_match_analysis("101")
    pred_id = brain.track_match(canonical)
    row = mt.get_prediction_by_id(pred_id)
    snapshot = (row.get("model_factors") or {}).get("canonical_snapshot")
    assert snapshot is not None
    assert snapshot["evaluation_status"] == "OPEN"
    assert "edge_score" in snapshot


def test_calibration_ignores_open_rows():
    rows = [
        {"status": "completed", "is_correct": True, "confidence": 80},
        {"status": "pending", "is_correct": None, "confidence": 90},
    ]
    result = calibration_service.get_calibration(rows)
    assert result["sample_size"] == 1


def test_model_trust_requires_minimum_sample():
    trust = model_trust_service.compute_trust_score(
        calibration_score=0.9,
        recent_accuracy=0.8,
        average_data_quality=80,
        sample_size=3,
    )
    assert trust["trust_score"] is None
    assert trust["label"] == "Insufficient Data"


def test_routes_do_not_recompute_action_outside_decision_engine():
    payload = {
        "win_probabilities": {"a": 55, "draw": 20, "b": 25},
        "best_pick": {"prediction": "Arsenal"},
        "confidence_pct": 80,
        "data_completeness": {"tier": "strong"},
    }
    with patch.object(flask_app_module.DecisionEngine, "build_decision", return_value={
        "side": "Arsenal",
        "action": "SKIP",
        "confidence": 80,
        "probabilities": {"home": 55, "draw": 20, "away": 25},
        "model_probability": 0.8,
        "implied_probability": None,
        "edge_score": None,
        "risk_level": "HIGH",
        "risk_score": 0.8,
        "expected_value": None,
        "decision_grade": "C",
        "data_quality": 80,
        "reasoning": {"strengths": ["x"], "risks": ["y"]},
    }):
        analysis = flask_app_module._analysis_from_prediction_payload(payload, match_id="1", matchup="Arsenal vs Chelsea")
    assert analysis["action"] == "SKIP"


def test_soccer_card_and_match_analysis_share_quant_fields():
    fixture = _fixture()
    with patch.object(flask_app_module, "_MATCH_BRAIN") as brain:
        canonical = {
            "match_id": "101",
            "matchup": "Arsenal vs Chelsea",
            "league": "Premier League",
            "kickoff": "2026-04-24T15:00:00+00:00",
            "status": "scheduled",
            "recommended_side": "Arsenal",
            "action": "BET",
            "confidence": 66,
            "probabilities": {"home": 52.0, "draw": 24.0, "away": 24.0},
            "data_quality": 85,
            "reason": "Stronger recent form",
            "metric_breakdown": {
                "model_probability": 0.66,
                "implied_probability": 0.52,
                "edge_score": 0.14,
                "expected_value": 0.14,
                "risk_score": 0.2,
                "risk_level": "MEDIUM",
                "decision_grade": "B",
            },
            "prediction": {
                "side": "Arsenal",
                "action": "BET",
                "confidence": 66,
                "probabilities": {"home": 52.0, "draw": 24.0, "away": 24.0},
                "model_probability": 0.66,
                "implied_probability": 0.52,
                "edge_score": 0.14,
                "expected_value": 0.14,
                "risk_score": 0.2,
                "risk_level": "MEDIUM",
                "decision_grade": "B",
                "data_quality": 85,
                "reasoning": {"strengths": ["Stronger recent form"], "risks": ["x"]},
            },
        }
        brain.canonical_from_fixture.return_value = canonical
        analysis = flask_app_module._analysis_from_fixture(fixture)
        card = flask_app_module._soccer_card_from_fixture_analysis(fixture, analysis)
    assert analysis["edge_score"] == 0.14
    assert analysis["expected_value"] == 0.14
    assert card["action"] == analysis["action"]
