from __future__ import annotations

from typing import Any, Callable
import logging

from services import cache_service
from services.prediction_contract import validate_analysis


_deps: dict[str, Callable[..., Any]] = {}
_log = logging.getLogger(__name__)


def configure(**deps: Callable[..., Any]) -> None:
    _deps.update(deps)


def get_match_analysis(match_id: str | int):
    key = cache_service.make_key("match-analysis", match_id)
    cached = cache_service.get_json(key)
    if cached is not None:
        try:
            return validate_analysis(cached)
        except Exception:
            cache_service.delete(key)
    analyze_fn = _deps.get("analyze_match")
    if not analyze_fn:
        return None
    result = analyze_fn(match_id)
    try:
        validated = validate_analysis(result)
        cache_service.set_json(key, validated, ttl=300)
        return validated
    except Exception as exc:
        _log.warning("analysis_contract_validation_failed match_id=%s error=%s", match_id, exc)
    return result


def get_fixture_cards(league_id: int):
    fixture_key = cache_service.make_key("fixtures", league_id)
    payload = cache_service.get_json(fixture_key)
    if payload is None:
        load_fn = _deps.get("load_fixtures")
        if not load_fn:
            return [], [], None, "Unavailable", ""
        try:
            payload = load_fn(league_id)
        except Exception:
            return [], [], "Unavailable", "degraded", ""
        cache_service.set_json(fixture_key, payload, ttl=120)
    if isinstance(payload, (list, tuple)) and len(payload) == 5:
        fixtures, load_error, source, marker, _meta = payload
    elif isinstance(payload, (list, tuple)) and len(payload) == 4:
        fixtures, load_error, source, marker = payload
    else:
        fixtures, load_error, source, marker = [], None, "Unavailable", ""

    cards: list[dict[str, Any]] = []
    for fixture in fixtures or []:
        fixture_id = (fixture.get("fixture") or {}).get("id")
        if fixture_id is None:
            continue
        analysis = get_match_analysis(str(fixture_id))
        if not analysis:
            continue
        build_fn = _deps.get("card_from_fixture")
        if build_fn:
            card = build_fn(fixture, analysis)
        else:
            card = _fallback_card(analysis)
        if card:
            cards.append(card)
    return cards, fixtures, load_error, source, marker


def get_top_opportunities(league_id: int):
    top_key = cache_service.make_key("top-opportunities", league_id)
    cached = cache_service.get_json(top_key)
    if cached is not None:
        return cached
    cards, *_ = get_fixture_cards(league_id)
    top_fn = _deps.get("top_opportunities")
    result = top_fn(cards, 4) if top_fn else cards[:4]
    cache_service.set_json(top_key, result, ttl=120)
    return result


def get_today_plan(league_id: int):
    plan_key = cache_service.make_key("today-plan", league_id)
    cached = cache_service.get_json(plan_key)
    if cached is not None:
        return cached
    cards, *_ = get_fixture_cards(league_id)
    plan_fn = _deps.get("plan_summary")
    result = plan_fn(cards) if plan_fn else {"bet": 0, "consider": 0, "skip": 0}
    cache_service.set_json(plan_key, result, ttl=120)
    return result


def _fallback_card(analysis: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(analysis, dict):
        return None
    probs = analysis.get("probabilities") or {}
    team_a = str(analysis.get("team_a") or analysis.get("home_name") or "Home")
    team_b = str(analysis.get("team_b") or analysis.get("away_name") or "Away")
    action = str(analysis.get("action") or "SKIP").upper()
    confidence = int(round(float(analysis.get("confidence") or 0)))
    probability_rows = [
        {"label": team_a, "value": max(0.0, min(100.0, float((probs.get("a", probs.get("home")) or 0.0))))},
        {"label": "Draw", "value": max(0.0, min(100.0, float((probs.get("draw") or 0.0))))},
        {"label": team_b, "value": max(0.0, min(100.0, float((probs.get("b", probs.get("away")) or 0.0))))},
    ]
    return {
        "match_id": analysis.get("match_id"),
        "matchup": analysis.get("matchup") or analysis.get("match", "Match"),
        "team_a": team_a,
        "team_b": team_b,
        "team_a_initials": team_a[:2].upper(),
        "team_b_initials": team_b[:2].upper(),
        "competition": analysis.get("league") or "Soccer",
        "confidence": confidence,
        "confidence_pct": confidence,
        "action": action,
        "action_label": action.title(),
        "action_class": "bet" if action == "BET" else "consider" if action == "CONSIDER" else "skip",
        "recommended_side": analysis.get("recommended_side"),
        "probabilities": {
            "a": probs.get("a", probs.get("home")),
            "draw": probs.get("draw"),
            "b": probs.get("b", probs.get("away")),
        },
        "probability_rows": probability_rows,
        "data_confidence": {"state": "partial", "label": str(analysis.get("data_quality") or "Partial")},
        "reason": analysis.get("reason"),
        "data_quality": analysis.get("data_quality"),
        "metric_breakdown": analysis.get("metric_breakdown"),
        "cta_url": f"/prediction?match_id={analysis.get('match_id')}" if analysis.get("match_id") else "/prediction",
        "cta_method": "get",
        "cta_payload": {},
    }
