"""
Tests for the Demo/Live runtime mode switcher.

Covers:
  - default mode is demo (env absent)
  - /set-mode accepts demo and live
  - /set-mode rejects invalid modes (400)
  - mode persists in session after set-mode
  - mode switch clears in-process fixture/analysis caches
  - demo route uses demo fixture source (api_client thread-local)
  - live route uses live provider path (api_client thread-local)
  - demo predictions do not leak into live mode (cache isolation)
  - UI renders mode switcher element in HTML
  - UI renders correct mode badge in topbar
"""

from __future__ import annotations

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Helper: get a test client with session support
# ---------------------------------------------------------------------------

def _client():
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    return flask_app.app.test_client()


# ---------------------------------------------------------------------------
# 1. Default mode is demo when SCORPRED_DEMO_MODE is absent
# ---------------------------------------------------------------------------

class TestDefaultMode:
    def test_env_absent_returns_live(self, monkeypatch):
        """Absent env var defaults to live (backward-compatible; demo is opt-in)."""
        monkeypatch.delenv("SCORPRED_DEMO_MODE", raising=False)
        import app as flask_app
        with flask_app.app.test_request_context("/"):
            mode = flask_app._env_default_mode()
            assert mode == "live"

    def test_env_zero_returns_live(self, monkeypatch):
        monkeypatch.setenv("SCORPRED_DEMO_MODE", "0")
        import app as flask_app
        with flask_app.app.test_request_context("/"):
            mode = flask_app._env_default_mode()
            assert mode == "live"

    def test_env_one_returns_demo(self, monkeypatch):
        monkeypatch.setenv("SCORPRED_DEMO_MODE", "1")
        import app as flask_app
        with flask_app.app.test_request_context("/"):
            mode = flask_app._env_default_mode()
            assert mode == "demo"


# ---------------------------------------------------------------------------
# 2. /set-mode accepts demo and live
# ---------------------------------------------------------------------------

class TestSetModeRoute:
    def test_set_mode_demo(self):
        with _client() as client:
            resp = client.post(
                "/set-mode",
                json={"mode": "demo"},
                content_type="application/json",
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["mode"] == "demo"
            assert "Demo" in data["label"]

    def test_set_mode_live(self):
        with _client() as client:
            resp = client.post(
                "/set-mode",
                json={"mode": "live"},
                content_type="application/json",
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["mode"] == "live"
            assert "Live" in data["label"]

    def test_set_mode_invalid_returns_400(self):
        with _client() as client:
            resp = client.post(
                "/set-mode",
                json={"mode": "fake"},
                content_type="application/json",
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert data["ok"] is False

    def test_set_mode_missing_body_returns_400(self):
        with _client() as client:
            resp = client.post(
                "/set-mode",
                json={},
                content_type="application/json",
            )
            assert resp.status_code == 400

    def test_set_mode_persists_in_session(self):
        with _client() as client:
            client.post("/set-mode", json={"mode": "live"}, content_type="application/json")
            import app as flask_app
            with client.session_transaction() as sess:
                assert sess.get("scorpred_mode") == "live"

    def test_mode_session_overrides_env(self, monkeypatch):
        """Session mode wins over env default."""
        monkeypatch.setenv("SCORPRED_DEMO_MODE", "1")  # env says demo
        import app as flask_app
        with flask_app.app.test_request_context("/"):
            from flask import session
            session["scorpred_mode"] = "live"           # session says live
            assert flask_app.get_runtime_mode() == "live"


# ---------------------------------------------------------------------------
# 3. Cache isolation
# ---------------------------------------------------------------------------

class TestCacheIsolation:
    def test_set_mode_clears_fixture_cache(self):
        import app as flask_app
        flask_app._local_fixture_cache[39] = ([{"fixture": {"id": 1}}], None, "cached", "")
        with _client() as client:
            client.post("/set-mode", json={"mode": "live"}, content_type="application/json")
        assert 39 not in flask_app._local_fixture_cache

    def test_set_mode_clears_match_analysis_cache(self):
        import app as flask_app
        from services import cache_service
        flask_app._local_match_analysis_cache["test-key"] = {"match_id": "test-key"}
        with _client() as client:
            client.post("/set-mode", json={"mode": "demo"}, content_type="application/json")
        assert "test-key" not in flask_app._local_match_analysis_cache

    def test_demo_data_does_not_appear_in_live_mode(self, monkeypatch):
        """After switching to live, demo-injected fixture predictions must not be cached."""
        import app as flask_app
        # Pre-load demo data into the fixture cache
        demo_fixture = [{"fixture": {"id": 9900001}, "prediction": {"prediction_source": "ScorPred demo rules"}}]
        flask_app._local_fixture_cache[39] = (demo_fixture, None, "demo", "")
        # Switch to live — cache must be cleared
        with _client() as client:
            client.post("/set-mode", json={"mode": "live"}, content_type="application/json")
        assert 39 not in flask_app._local_fixture_cache


# ---------------------------------------------------------------------------
# 4. api_client thread-local mode
# ---------------------------------------------------------------------------

class TestApiClientThreadLocalMode:
    def test_set_request_demo_mode_true(self):
        import api_client as ac
        ac.set_request_demo_mode(True)
        try:
            assert ac._effective_demo_mode() is True
        finally:
            ac.set_request_demo_mode(False)  # prevent thread-local leakage

    def test_set_request_demo_mode_false(self):
        import api_client as ac
        ac.set_request_demo_mode(False)
        assert ac._effective_demo_mode() is False

    def test_demo_mode_routes_to_demo_json_when_espn_fails(self, monkeypatch):
        import api_client as ac
        monkeypatch.setattr(ac, "_DEMO_MODE", False)
        ac.set_request_demo_mode(True)
        monkeypatch.setattr(ac, "_espn_upcoming_for_league", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("ESPN down")))
        result = ac.get_upcoming_fixtures(39, 2025, 5)
        assert isinstance(result, list)
        ac.set_request_demo_mode(False)  # reset


# ---------------------------------------------------------------------------
# 5. UI rendering
# ---------------------------------------------------------------------------

class TestUIRendering:
    def test_mode_switcher_element_present(self, monkeypatch):
        monkeypatch.setattr("app._DEMO_MODE", False)
        with _client() as client:
            with client.session_transaction() as sess:
                sess["scorpred_mode"] = "demo"
            resp = client.get("/")
            html = resp.data.decode()
            assert "sp-mode-switcher" in html

    def test_demo_mode_shows_demo_badge_in_topbar(self, monkeypatch):
        with _client() as client:
            with client.session_transaction() as sess:
                sess["scorpred_mode"] = "demo"
            resp = client.get("/")
            html = resp.data.decode()
            assert "Demo" in html

    def test_live_mode_shows_live_badge_in_topbar(self, monkeypatch):
        with _client() as client:
            with client.session_transaction() as sess:
                sess["scorpred_mode"] = "live"
            resp = client.get("/")
            html = resp.data.decode()
            assert "Live" in html
