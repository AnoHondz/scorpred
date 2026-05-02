from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from services import cache_service

_FIXTURE_CARD_TTL = 900      # 15 min
_MATCH_ANALYSIS_TTL = 1800   # 30 min
_TOP_OPP_TTL = 900
_TODAY_PLAN_TTL = 900

_deps: dict[str, Callable[..., Any]] = {}


def configure(**deps: Callable[..., Any]) -> None:
    _deps.update(deps)


def get_match_analysis(match_id: str | int):
    key = cache_service.make_key("match-analysis", match_id)
    cached = cache_service.get_json(key, ttl=_MATCH_ANALYSIS_TTL)
    if cached is not None:
        return cached
    analyze_fn = _deps.get("analyze_match")
    if not analyze_fn:
        return None
    result = analyze_fn(match_id)
    if result is not None:
        cache_service.set_json(key, result, ttl=_MATCH_ANALYSIS_TTL)
    return result


def get_fixture_cards(league_id: int):
    fixture_key = cache_service.make_key("fixtures", league_id)
    payload = cache_service.get_json(fixture_key, ttl=_FIXTURE_CARD_TTL)
    if payload is None:
        load_fn = _deps.get("load_fixtures")
        if not load_fn:
            return [], None, "Unavailable", "", ""
        payload = load_fn(league_id)
        cache_service.set_json(fixture_key, payload, ttl=_FIXTURE_CARD_TTL)
    fixtures, load_error, source, marker = payload

    build_fn = _deps.get("card_from_fixture")
    if not build_fn:
        return [], fixtures, load_error, source, marker

    valid = [f for f in (fixtures or []) if (f.get("fixture") or {}).get("id") is not None]

    def _analyze_and_build(fixture: dict) -> dict | None:
        fixture_id = (fixture.get("fixture") or {}).get("id")
        try:
            analysis = get_match_analysis(str(fixture_id))
        except Exception:
            analysis = None
        if not analysis:
            return None
        try:
            return build_fn(fixture, analysis)
        except Exception:
            return None

    cards: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for card in pool.map(_analyze_and_build, valid):
            if card:
                cards.append(card)

    return cards, fixtures, load_error, source, marker


def get_top_opportunities(league_id: int):
    top_key = cache_service.make_key("top-opportunities", league_id)
    cached = cache_service.get_json(top_key, ttl=_TOP_OPP_TTL)
    if cached is not None:
        return cached
    cards, *_ = get_fixture_cards(league_id)
    top_fn = _deps.get("top_opportunities")
    result = top_fn(cards, 4) if top_fn else cards[:4]
    cache_service.set_json(top_key, result, ttl=_TOP_OPP_TTL)
    return result


def get_today_plan(league_id: int):
    plan_key = cache_service.make_key("today-plan", league_id)
    cached = cache_service.get_json(plan_key, ttl=_TODAY_PLAN_TTL)
    if cached is not None:
        return cached
    cards, *_ = get_fixture_cards(league_id)
    plan_fn = _deps.get("plan_summary")
    result = plan_fn(cards) if plan_fn else {"bet": 0, "consider": 0, "skip": 0}
    cache_service.set_json(plan_key, result, ttl=_TODAY_PLAN_TTL)
    return result
