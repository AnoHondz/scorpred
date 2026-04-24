from __future__ import annotations

from unittest.mock import patch

import app as flask_app_module
import model_tracker as mt
from services.decision_engine import DecisionEngine
from services.match_brain import MatchBrain


def _fixture(fid: int = 101):
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
            "edge_score": 5.0,
            "risk_level": "LOW",
            "expected_value": 5.0,
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
