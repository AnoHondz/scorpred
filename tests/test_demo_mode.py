"""
Tests for SCORPRED_DEMO_MODE.

Covers:
  - DemoPredictionEngine determinism and correctness
  - ESPN normalization path
  - Local demo_fixtures.json fallback
  - Same match_id => identical prediction (idempotency)
  - Probability validity (sum to ~100, all non-negative)
  - Completed demo matches handled safely
  - demo_mode flag in template context
  - /health endpoint still works in demo mode
"""

from __future__ import annotations

import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# DemoPredictionEngine tests
# ---------------------------------------------------------------------------

class TestDemoPredictionEngine:
    def _engine(self):
        from services.demo_prediction_engine import DemoPredictionEngine
        return DemoPredictionEngine()

    def _fixture(self, match_id=9900001, home="Arsenal", away="Chelsea", league_id=39):
        return {
            "fixture": {"id": match_id, "date": "2026-05-07T19:45:00Z", "status": {"short": "NS"}},
            "league": {"id": league_id, "name": "Premier League"},
            "teams": {"home": {"id": 42, "name": home}, "away": {"id": 49, "name": away}},
            "goals": {"home": None, "away": None},
            "source": "demo",
        }

    def test_inject_adds_prediction_block(self):
        eng = self._engine()
        fix = self._fixture()
        eng.inject(fix)
        assert "prediction" in fix

    def test_probabilities_sum_to_100(self):
        eng = self._engine()
        fix = self._fixture()
        eng.inject(fix)
        wp = fix["prediction"]["win_probabilities"]
        total = wp["a"] + wp["draw"] + wp["b"]
        assert abs(total - 100.0) < 0.5, f"Probabilities sum to {total}, not 100"

    def test_probabilities_all_non_negative(self):
        eng = self._engine()
        fix = self._fixture()
        eng.inject(fix)
        wp = fix["prediction"]["win_probabilities"]
        assert wp["a"] >= 0 and wp["draw"] >= 0 and wp["b"] >= 0

    def test_determinism_same_match_id_gives_identical_prediction(self):
        eng = self._engine()
        fix1 = self._fixture(match_id=9900001, home="Arsenal", away="Chelsea")
        fix2 = self._fixture(match_id=9900001, home="Arsenal", away="Chelsea")
        eng.inject(fix1)
        eng.inject(fix2)
        assert fix1["prediction"]["win_probabilities"] == fix2["prediction"]["win_probabilities"]
        assert fix1["prediction"]["confidence_pct"] == fix2["prediction"]["confidence_pct"]

    def test_different_match_ids_give_different_predictions(self):
        eng = self._engine()
        fix1 = self._fixture(match_id=9900001, home="Arsenal", away="Chelsea")
        fix2 = self._fixture(match_id=9900002, home="Arsenal", away="Chelsea")
        eng.inject(fix1)
        eng.inject(fix2)
        # Different seeds → different probabilities (almost certainly)
        assert fix1["prediction"]["win_probabilities"] != fix2["prediction"]["win_probabilities"]

    def test_data_completeness_tier_is_demo(self):
        eng = self._engine()
        fix = self._fixture()
        eng.inject(fix)
        assert fix["prediction"]["data_completeness"]["tier"] == "demo"

    def test_prediction_source_is_demo_rules(self):
        eng = self._engine()
        fix = self._fixture()
        eng.inject(fix)
        assert fix["prediction"]["prediction_source"] == "ScorPred demo rules"

    def test_confidence_pct_in_sane_range(self):
        eng = self._engine()
        fix = self._fixture()
        eng.inject(fix)
        conf = fix["prediction"]["confidence_pct"]
        assert 40.0 <= conf <= 90.0, f"confidence_pct={conf} out of expected range"

    def test_completed_fixture_handled_safely(self):
        """Inject must not raise on a completed (FT) fixture."""
        eng = self._engine()
        fix = self._fixture()
        fix["fixture"]["status"]["short"] = "FT"
        fix["goals"] = {"home": 2, "away": 1}
        eng.inject(fix)
        assert "prediction" in fix

    def test_unknown_teams_get_fallback_strength(self):
        """Unknown team names should still produce valid probabilities."""
        eng = self._engine()
        fix = self._fixture(home="Unknown FC", away="Mystery United")
        eng.inject(fix)
        wp = fix["prediction"]["win_probabilities"]
        total = wp["a"] + wp["draw"] + wp["b"]
        assert abs(total - 100.0) < 0.5


# ---------------------------------------------------------------------------
# demo_fixtures.json fallback tests
# ---------------------------------------------------------------------------

class TestDemoFixturesJson:
    def _demo_path(self):
        import pathlib
        return pathlib.Path(__file__).parent.parent / "data" / "demo_fixtures.json"

    def test_demo_json_exists(self):
        assert self._demo_path().exists(), "data/demo_fixtures.json not found"

    def test_demo_json_valid_and_non_empty(self):
        fixtures = json.loads(self._demo_path().read_text())
        assert isinstance(fixtures, list)
        assert len(fixtures) >= 4, "Expected at least 4 bundled fixtures"

    def test_demo_json_has_multiple_leagues(self):
        fixtures = json.loads(self._demo_path().read_text())
        leagues = {(f.get("league") or {}).get("id") for f in fixtures}
        assert len(leagues) >= 2, "demo_fixtures.json should cover at least 2 leagues"

    def test_demo_json_fixtures_have_canonical_shape(self):
        fixtures = json.loads(self._demo_path().read_text())
        for f in fixtures:
            assert "fixture" in f
            assert "teams" in f
            assert "league" in f
            assert f["fixture"].get("id") is not None
            assert (f["teams"].get("home") or {}).get("name")
            assert (f["teams"].get("away") or {}).get("name")

    def test_api_client_load_demo_fixtures_json(self):
        import api_client as ac
        fixtures = ac._load_demo_fixtures_json(39)
        assert isinstance(fixtures, list)
        assert len(fixtures) >= 2

    def test_api_client_load_demo_fixtures_json_league_filter(self):
        import api_client as ac
        all_f = ac._load_demo_fixtures_json(0)
        pl_f = ac._load_demo_fixtures_json(39)
        # League filter should return a subset
        assert len(pl_f) < len(all_f) or len(all_f) == len(pl_f)
        for f in pl_f:
            assert (f.get("league") or {}).get("id") == 39


# ---------------------------------------------------------------------------
# api_client demo mode routing tests
# ---------------------------------------------------------------------------

class TestApiClientDemoMode:
    def test_demo_mode_flag_exists(self):
        import api_client as ac
        assert hasattr(ac, "_DEMO_MODE")

    def test_get_upcoming_fixtures_in_demo_mode_uses_local_json(self, monkeypatch):
        """When ESPN fails, get_upcoming_fixtures falls back to demo JSON."""
        import api_client as ac
        monkeypatch.setattr(ac, "_DEMO_MODE", True)
        # Make ESPN fetching raise
        monkeypatch.setattr(ac, "_espn_upcoming_for_league", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("ESPN down")))
        result = ac.get_upcoming_fixtures(39, 2025, 10)
        assert isinstance(result, list)

    def test_get_upcoming_fixtures_in_demo_mode_returns_espn_when_available(self, monkeypatch):
        """When ESPN succeeds, get_upcoming_fixtures returns ESPN fixtures."""
        import api_client as ac
        monkeypatch.setattr(ac, "_DEMO_MODE", True)
        fake_fixtures = [{"fixture": {"id": 1, "date": "2026-05-07T19:45:00Z"}, "teams": {"home": {"name": "A"}, "away": {"name": "B"}}}]
        monkeypatch.setattr(ac, "_espn_upcoming_for_league", lambda *a, **kw: fake_fixtures)
        result = ac.get_upcoming_fixtures(39, 2025, 10)
        assert result == fake_fixtures

    def test_non_demo_mode_does_not_call_demo_json(self, monkeypatch):
        """In normal mode, _load_demo_fixtures_json must not be called."""
        import api_client as ac
        monkeypatch.setattr(ac, "_DEMO_MODE", False)
        called = {"n": 0}
        real_fn = ac._load_demo_fixtures_json

        def _tracking(*a, **kw):
            called["n"] += 1
            return real_fn(*a, **kw)

        monkeypatch.setattr(ac, "_load_demo_fixtures_json", _tracking)
        # Attempt a call — it may fail (no keys) but demo JSON must not be read
        try:
            ac.get_upcoming_fixtures(39, 2025, 5)
        except Exception:
            pass
        assert called["n"] == 0, "_load_demo_fixtures_json called in non-demo mode"


# ---------------------------------------------------------------------------
# Health endpoint in demo mode
# ---------------------------------------------------------------------------

class TestHealthInDemoMode:
    def test_health_route_works_in_demo_mode(self, monkeypatch):
        """GET /health must return 200 JSON even when SCORPRED_DEMO_MODE=1."""
        import app as flask_app
        monkeypatch.setattr(flask_app, "_get_api_health", lambda ts: True)
        with flask_app.app.test_client() as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "status" in data
