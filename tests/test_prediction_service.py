from __future__ import annotations

from services import cache_service, prediction_service


def setup_function():
    cache_service._local_cache.clear()
    prediction_service._deps.clear()


def test_get_match_analysis_rejects_invalid_contract():
    calls = {"count": 0}

    def _invalid(_match_id):
        calls["count"] += 1
        return {
            "match_id": "1",
            "confidence": 53,
            "probabilities": {"a": 38, "draw": 26, "b": 36},
            "action": "BET",
            "recommended_side": "Home",
            "reason": "fallback",
            "data_quality": "partial",
            "metric_breakdown": "Unavailable",
        }

    prediction_service.configure(
        analyze_match=_invalid
    )
    first = prediction_service.get_match_analysis("1")
    second = prediction_service.get_match_analysis("1")
    assert first is not None
    assert calls["count"] == 2


def test_get_match_analysis_valid_contract_is_cached():
    calls = {"count": 0}

    def _analyze(_match_id):
        calls["count"] += 1
        return {
            "match_id": "101",
            "action": "CONSIDER",
            "recommended_side": "Arsenal",
            "confidence": 64,
            "probabilities": {"a": 46, "draw": 29, "b": 25},
            "reason": "Form edge",
            "data_quality": 70,
            "metric_breakdown": None,
        }

    prediction_service.configure(analyze_match=_analyze)
    first = prediction_service.get_match_analysis("101")
    second = prediction_service.get_match_analysis("101")
    assert first is not None
    assert first == second
    assert calls["count"] == 1


def test_get_fixture_cards_uses_fallback_builder_when_not_configured():
    fixture = {
        "fixture": {"id": 77},
        "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
    }
    prediction_service.configure(
        load_fixtures=lambda _league: ([fixture], None, "configured", ""),
        analyze_match=lambda _match_id: {
            "match_id": "77",
            "action": "CONSIDER",
            "recommended_side": "A",
            "confidence": 61,
            "probabilities": {"a": 44, "draw": 30, "b": 26},
            "reason": "Edge",
            "data_quality": 70,
            "metric_breakdown": None,
        },
    )
    cards, fixtures, *_ = prediction_service.get_fixture_cards(39)
    assert fixtures
    assert cards
    assert cards[0]["match_id"] == "77"
