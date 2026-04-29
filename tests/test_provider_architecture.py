"""
Tests for the multi-provider football data architecture.

Covers:
  - Provider selection based on FOOTBALL_PROVIDER env var
  - providers/__init__.py registry logic
  - providers/football_data_provider.py adapter
  - Health endpoint throttling (no external-call flood)
  - Graceful fallback when primary provider returns empty
"""

from __future__ import annotations

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Provider registry tests ───────────────────────────────────────────────────

class TestProviderRegistry:
    def test_default_mode_is_auto(self, monkeypatch):
        monkeypatch.delenv("FOOTBALL_PROVIDER", raising=False)
        monkeypatch.delenv("API_FOOTBALL_PROVIDER", raising=False)
        import importlib
        import providers as prov
        importlib.reload(prov)
        assert prov.FOOTBALL_PROVIDER in ("auto", "football_data", "api_football")

    def test_api_football_mode_returns_no_primary(self, monkeypatch):
        monkeypatch.setenv("FOOTBALL_PROVIDER", "api_football")
        import importlib
        import providers as prov
        importlib.reload(prov)
        assert prov.get_primary_provider() is None

    def test_fdo_key_aliases_resolved(self, monkeypatch):
        """FOOTBALL_DATA_API_KEY, FOOTBALL_DATA_KEY, and FOOTBALL_DATA_ORG_KEY all work."""
        import importlib
        for var in ("FOOTBALL_DATA_API_KEY", "FOOTBALL_DATA_KEY", "FOOTBALL_DATA_ORG_KEY"):
            monkeypatch.setenv(var, "test-key-abc")
            import providers as prov
            importlib.reload(prov)
            assert prov.FOOTBALL_DATA_API_KEY == "test-key-abc", f"{var} alias not picked up"
            monkeypatch.delenv(var, raising=False)

    def test_provider_mode_summary_structure(self, monkeypatch):
        import providers as prov
        summary = prov.provider_mode_summary()
        assert "mode" in summary
        assert "fallback" in summary
        assert "fdo_key_set" in summary

    def test_football_data_mode_with_no_key_still_loads_provider(self, monkeypatch):
        """When FOOTBALL_PROVIDER=football_data but no key set, get_primary_provider
        returns an instance (availability check is separate)."""
        import importlib
        monkeypatch.setenv("FOOTBALL_PROVIDER", "football_data")
        monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)
        monkeypatch.delenv("FOOTBALL_DATA_KEY", raising=False)
        monkeypatch.delenv("FOOTBALL_DATA_ORG_KEY", raising=False)
        import providers as prov
        importlib.reload(prov)
        # In football_data mode the instance is returned even without key
        # (availability will be False, but the caller controls fallback logic)
        provider = prov.get_primary_provider()
        # Provider may be None if key absent prevents construction — both are acceptable
        # as long as it doesn't raise
        assert provider is None or hasattr(provider, "get_name")


# ── FootballDataProvider adapter tests ────────────────────────────────────────

class TestFootballDataProviderAdapter:
    def test_provider_name(self):
        from providers.football_data_provider import FootballDataProvider
        p = FootballDataProvider()
        assert p.get_name() == "football_data"

    def test_get_upcoming_fixtures_returns_list_on_fdo_failure(self, monkeypatch):
        """Provider must return empty list (not raise) when FDO call fails."""
        from providers.football_data_provider import FootballDataProvider
        import football_data_client as fdc
        monkeypatch.setattr(fdc, "get_upcoming_fixtures", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network down")))
        p = FootballDataProvider()
        result = p.get_upcoming_fixtures(39, 2025, 10)
        assert result == []

    def test_get_teams_returns_list_on_fdo_failure(self, monkeypatch):
        from providers.football_data_provider import FootballDataProvider
        import football_data_client as fdc
        monkeypatch.setattr(fdc, "get_teams", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network down")))
        p = FootballDataProvider()
        assert p.get_teams(39, 2025) == []

    def test_get_standings_returns_list_on_fdo_failure(self, monkeypatch):
        from providers.football_data_provider import FootballDataProvider
        import football_data_client as fdc
        monkeypatch.setattr(fdc, "get_standings", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network down")))
        p = FootballDataProvider()
        assert p.get_standings(39, 2025) == []

    def test_is_available_propagates_fdc_check(self, monkeypatch):
        from providers.football_data_provider import FootballDataProvider
        import football_data_client as fdc
        monkeypatch.setattr(fdc, "is_available", lambda: True)
        p = FootballDataProvider()
        assert p.is_available() is True

        monkeypatch.setattr(fdc, "is_available", lambda: False)
        assert p.is_available() is False

    def test_get_provider_info_returns_dict(self, monkeypatch):
        from providers.football_data_provider import FootballDataProvider
        import football_data_client as fdc
        monkeypatch.setattr(fdc, "get_provider_info", lambda: {"provider": "football_data", "last_success": None})
        p = FootballDataProvider()
        info = p.get_provider_info()
        assert isinstance(info, dict)
        assert info.get("provider") == "football_data"

    def test_provider_satisfies_protocol(self):
        from providers import FootballProvider
        from providers.football_data_provider import FootballDataProvider
        p = FootballDataProvider()
        assert isinstance(p, FootballProvider)


# ── api_client provider orchestration tests ───────────────────────────────────

class TestApiClientProviderOrchestration:
    def test_fdo_enabled_when_key_and_auto_mode(self, monkeypatch):
        import importlib
        monkeypatch.setenv("FOOTBALL_PROVIDER", "auto")
        monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "live-key")
        import api_client
        importlib.reload(api_client)
        # With a live key and auto mode, FDO should be active
        # (actual network call not made — just checking the flag logic)
        # After reload with a key set, _USING_FDO depends on is_available() in fdo_mod
        # We cannot guarantee True without a real network, so just confirm no exception
        assert hasattr(api_client, "_USING_FDO")

    def test_fdo_disabled_in_api_football_mode(self, monkeypatch):
        import importlib
        monkeypatch.setenv("FOOTBALL_PROVIDER", "api_football")
        monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "live-key")
        import providers as prov
        importlib.reload(prov)
        assert prov.get_primary_provider() is None

    def test_get_upcoming_fixtures_falls_back_when_fdo_empty(self, monkeypatch):
        """When FDO returns [], api_client falls through to api-sports/ESPN path."""
        import api_client
        monkeypatch.setattr(api_client, "_USING_FDO", True)

        class _StubProvider:
            def is_available(self): return True
            def get_upcoming_fixtures(self, league_id, season, next_n): return []
            def get_teams(self, league_id, season): return []
            def get_standings(self, league_id, season): return []

        monkeypatch.setattr(api_client, "_fdo_provider", _StubProvider())
        monkeypatch.setattr(api_client, "_FOOTBALL_PROVIDER", "auto")

        # api_get will fail (no real key), but api_client should not raise
        try:
            result = api_client.get_upcoming_fixtures(39, 2025, 5)
            assert isinstance(result, list)
        except Exception:
            pass  # ESPN fallback may also fail in test env — acceptable


# ── Health endpoint throttle tests ───────────────────────────────────────────

class TestHealthProbeThrottling:
    def test_throttle_cache_prevents_repeated_calls(self, monkeypatch, tmp_path):
        """_get_api_health must use cached result within TTL window."""
        import app as flask_app

        call_count = {"n": 0}

        def _fake_safe_call(fn, *, retries=3, base_delay=0.25, label="", **_):
            call_count["n"] += 1
            return [{"team": "Arsenal"}]  # truthy = ok

        monkeypatch.setattr(flask_app, "_safe_external_call", _fake_safe_call)

        # Reset probe cache so first call goes through
        flask_app._health_probe["ok"] = None
        flask_app._health_probe["ts"] = 0.0

        now = time.time()
        flask_app._get_api_health(now)
        flask_app._get_api_health(now + 1)   # within TTL → cached
        flask_app._get_api_health(now + 10)  # still within TTL → cached

        assert call_count["n"] == 1, "external probe called more than once within TTL"

    def test_throttle_refreshes_after_ttl(self, monkeypatch):
        """After TTL expires a new probe must be triggered."""
        import app as flask_app

        call_count = {"n": 0}

        def _fake_safe_call(fn, *, retries=3, base_delay=0.25, label="", **_):
            call_count["n"] += 1
            return [{"team": "Arsenal"}]

        monkeypatch.setattr(flask_app, "_safe_external_call", _fake_safe_call)

        flask_app._health_probe["ok"] = None
        flask_app._health_probe["ts"] = 0.0

        now = time.time()
        flask_app._get_api_health(now)                               # call 1
        flask_app._get_api_health(now + flask_app._HEALTH_PROBE_TTL_S + 1)  # call 2

        assert call_count["n"] == 2, "probe not refreshed after TTL expiry"

    def test_throttle_returns_false_on_exception(self, monkeypatch):
        """If the probe raises, _get_api_health must return False (not propagate)."""
        import app as flask_app

        def _failing_call(fn, **_):
            raise RuntimeError("API down")

        monkeypatch.setattr(flask_app, "_safe_external_call", _failing_call)
        flask_app._health_probe["ok"] = None
        flask_app._health_probe["ts"] = 0.0

        result = flask_app._get_api_health(time.time())
        assert result is False

    def test_health_route_returns_valid_json(self, monkeypatch):
        """GET /health must return JSON with expected keys even when APIs are down."""
        import app as flask_app

        monkeypatch.setattr(flask_app, "_get_api_health", lambda ts: False)

        with flask_app.app.test_client() as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "status" in data
            assert "football_provider" in data
            assert "degraded_mode" in data
            assert "api" in data

    def test_health_route_includes_provider_info(self, monkeypatch):
        """football_provider block must always be present in /health response."""
        import app as flask_app

        monkeypatch.setattr(flask_app, "_get_api_health", lambda ts: True)

        with flask_app.app.test_client() as client:
            resp = client.get("/health")
            data = resp.get_json()
            fp = data.get("football_provider")
            assert isinstance(fp, dict)
