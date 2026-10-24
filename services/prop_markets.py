"""Optional sportsbook comparisons, independent of prop models and pick rankings.

Uses the existing The Odds API credential, never sportsbook scraping. Only exact
participants, kickoff, full player names and documented full-game markets join.
No market quote is treated as validation of a model or a betting recommendation.
"""
import hashlib
import math
import os
import re
import threading
import unicodedata
from collections import Counter
from datetime import UTC, datetime, timedelta

import requests

from services import cache_service
from services.prediction_lifecycle import is_pregame, parse_kickoff

BASE = "https://api.the-odds-api.com/v4/sports"
BOOKS = ("draftkings", "fanduel")
TTL = 300
QUOTE_TTL = 900
MONTHLY_CREDIT_CAP = 100  # Conservative local ceiling; never purchases extra quota.
_lock = threading.RLock()
SPORTS = {"nfl": "americanfootball_nfl", "nba": "basketball_nba"}
LEAGUES = {39: "soccer_epl", 61: "soccer_france_ligue_one", 78: "soccer_germany_bundesliga",
           135: "soccer_italy_serie_a", 140: "soccer_spain_la_liga", 253: "soccer_usa_mls"}
MARKETS = {
    "nfl": {"passing_yards": "player_pass_yds", "completions": "player_pass_completions",
            "passing_attempts": "player_pass_attempts", "passing_tds": "player_pass_tds",
            "interceptions": "player_pass_interceptions", "rushing_yards": "player_rush_yds",
            "carries": "player_rush_attempts", "receptions": "player_receptions",
            "receiving_yards": "player_reception_yds", "rush_rec_yards": "player_rush_reception_yds"},
    "nba": {"points": "player_points", "rebounds": "player_rebounds", "assists": "player_assists",
            "threes": "player_threes", "pra": "player_points_rebounds_assists"},
    "soccer": {"shots": "player_shots", "shots_on_target": "player_shots_on_target", "assists": "player_assists"},
}
MESSAGES = {
    "not_configured": "Sportsbook comparison unavailable: no live player-prop odds feed is configured.",
    "disabled": "Sportsbook comparison is disabled.",
    "unsupported": "No supported sportsbook market is available for these props or this competition.",
    "unavailable": "Sportsbook prices could not be refreshed. Historical targets remain available.",
    "authentication_failed": "The sportsbook odds provider did not accept the configured credential.",
    "rate_limited": "The sportsbook odds provider's request limit was reached.",
    "budget_exhausted": "The local sportsbook comparison credit limit has been reached for this month.",
    "no_match": "No exact upcoming matchup was found in the sportsbook feed.",
    "no_quotes": "No fresh matching sportsbook quotes are available for these players and markets.",
    "started": "Pregame sportsbook comparisons are unavailable after kickoff.",
    "no_picks": "No supported player props are available to compare.",
}


def _name(value):
    # Full names only. No surname-only, substring, suffix-dropping or fuzzy joins.
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", text)


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def _fetch(sport_key, suffix, params, credential, now, cost=0):
    """Single-flight cached reads; failures never log credential-bearing URLs.

    Reserve the maximum request cost before sending. Failed/empty requests also
    consume the local allowance conservatively. Provider-wide quotas still apply.
    """
    identity = hashlib.sha256(credential.encode()).hexdigest()[:16]
    key = cache_service.make_key("prop-odds-v1", identity, sport_key, suffix, sorted(params.items()))
    with _lock:
        cached = cache_service.get_json(key, ttl=TTL)
        if cached is not None:
            return cached
        if cost:
            budget_key = cache_service.make_key("prop-odds-budget-v1", identity, now.strftime("%Y-%m"))
            budget = cache_service.get_json(budget_key, ttl=32 * 86400) or {"reserved": 0}
            if budget["reserved"] + cost > MONTHLY_CREDIT_CAP:
                return {"status": "budget_exhausted"}
            cache_service.set_json(budget_key, {"reserved": budget["reserved"] + cost}, ttl=32 * 86400)
        try:
            response = requests.get(f"{BASE}/{sport_key}/{suffix}", params={**params, "apiKey": credential}, timeout=(3, 6))
            if response.status_code in {401, 403, 422, 429}:
                status = "rate_limited" if response.status_code == 429 else "authentication_failed" if response.status_code in {401, 403} else "unsupported"
                result = {"status": status}
            else:
                response.raise_for_status()
                result = {"status": "available", "payload": response.json(), "fetched_at": datetime.now(UTC).isoformat()}
        except (requests.RequestException, ValueError, TypeError):
            result = {"status": "unavailable"}
        cache_service.set_json(key, result, ttl=TTL if result["status"] == "available" else 60)
        return result


def _same_game(event, home, away, kickoff):
    if not isinstance(event, dict):
        return False
    start = parse_kickoff(event.get("commence_time"))
    return bool(start and _name(home) and _name(away) and abs((start - kickoff).total_seconds()) <= 300
                and _name(event.get("home_team")) == _name(home)
                and _name(event.get("away_team")) == _name(away))


def _quotes(payload, market_keys, kickoff, fetched_at, now):
    quotes = []
    fetched = parse_kickoff(fetched_at)
    if not fetched or not 0 <= (now - fetched).total_seconds() < TTL:
        return quotes
    def items(value):
        return value if isinstance(value, list) else []
    for book in items(payload.get("bookmakers")):
        if not isinstance(book, dict) or book.get("key") not in BOOKS or not book.get("title"):
            continue
        for market in items(book.get("markets")):
            if not isinstance(market, dict) or not isinstance(market.get("key"), str) or market["key"] not in market_keys:
                continue
            updated = parse_kickoff(market.get("last_update"))
            if not updated or not 0 <= (now - updated).total_seconds() < QUOTE_TTL:
                continue
            pairs = {}
            for outcome in items(market.get("outcomes")):
                if not isinstance(outcome, dict) or not isinstance(outcome.get("name"), str) or outcome["name"] not in {"Over", "Under"}:
                    continue
                point, price = _number(outcome.get("point")), _number(outcome.get("price"))
                player = _name(outcome.get("description"))
                if not player or point is None or point < 0 or price is None or price <= 1:
                    continue
                pair = pairs.setdefault((player, point), {})
                side = outcome["name"].lower()
                # Conflicting duplicate outcomes are ambiguous, not a best-price opportunity.
                pair[side] = price if side not in pair else None
            for (player, point), pair in pairs.items():
                if not pair.get("over") or not pair.get("under"):
                    continue
                quotes.append({"player": player, "market": market["key"], "line": point,
                               "over_decimal": pair["over"], "under_decimal": pair["under"],
                               "bookmaker": str(book["title"])[:80], "bookmaker_key": book["key"],
                               "updated_at": updated.isoformat(), "fetched_at": fetched_at,
                               "expires_at": min(kickoff, fetched + timedelta(seconds=TTL),
                                                 updated + timedelta(seconds=QUOTE_TTL)).isoformat()})
    return quotes


def snapshot(sport, home, away, kickoff, market_keys, league_id=None):
    now = datetime.now(UTC)
    kickoff = parse_kickoff(kickoff)
    if not kickoff or not is_pregame(kickoff, now=now):
        return {"status": "started", "quotes": []}
    credential = os.getenv("ODDS_API_KEY", "").strip()
    if not credential or credential.startswith("your_"):
        return {"status": "not_configured", "quotes": []}
    if os.getenv("PROP_ODDS_ENABLED", "1") != "1":
        return {"status": "disabled", "quotes": []}
    try:
        sport_key = LEAGUES.get(int(league_id or 0)) if sport == "soccer" else SPORTS.get(sport)
    except (ValueError, TypeError):
        sport_key = None
    if not sport_key or not market_keys:
        return {"status": "unsupported", "quotes": []}
    events = _fetch(sport_key, "events", {}, credential, now)
    if events["status"] != "available":
        return {"status": events["status"], "quotes": []}
    games = events.get("payload")
    matches = [event for event in games if _same_game(event, home, away, kickoff)] if isinstance(games, list) else []
    if len(matches) != 1 or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", str(matches[0].get("id") or "")):
        return {"status": "no_match", "quotes": []}
    event_id = matches[0]["id"]
    result = _fetch(sport_key, f"events/{event_id}/odds",
                    {"bookmakers": ",".join(BOOKS), "markets": ",".join(sorted(market_keys)),
                     "oddsFormat": "decimal", "dateFormat": "iso"}, credential, now, cost=len(market_keys))
    payload = result.get("payload")
    checked_at = datetime.now(UTC)
    if result["status"] != "available":
        return {"status": result["status"], "quotes": []}
    if (not is_pregame(kickoff, now=checked_at) or not _same_game(payload, home, away, kickoff)
            or payload.get("id") != event_id):
        return {"status": "no_match", "quotes": []}
    quotes = _quotes(payload, market_keys, kickoff, result.get("fetched_at"), checked_at)
    return {"status": "available" if quotes else "no_quotes", "quotes": quotes, "event_id": event_id}


def _model_at_line(pick, line):
    """Use the existing distribution and shrink, with no refit or extrapolation.

    Whole-number lines can push: omit comparisons until their settlement contract
    is supported. A truncated ladder cannot support a line outside its range.
    """
    if line % 1 != 0.5 or pick.get("side") not in {"over", "under"}:
        return None
    ladder = pick.get("ladder") or {}
    start, over = ladder.get("start"), ladder.get("over")
    if not isinstance(start, int) or isinstance(start, bool) or not isinstance(over, list):
        return None
    values = [_number(value) for value in over]
    if (not values or any(value is None or not 0 <= value <= 1 for value in values)
            or any(a < b for a, b in zip(values, values[1:]))):
        return None
    index = math.floor(line) - start
    if not 0 <= index < len(values):
        return None
    raw, shown = _number(pick.get("probability")), _number(pick.get("chance"))
    if raw is None or shown is None or not 0 <= raw <= 1 or not 0 <= shown <= 1:
        return None
    if raw == 0.5:
        if shown != 0.5:
            return None
        shrink = 1
    else:
        shrink = (shown - 0.5) / (raw - 0.5)
    if not 0 <= shrink <= 1.00001:
        return None
    probability = values[index] if pick["side"] == "over" else 1 - values[index]
    return round(0.5 + min(shrink, 1) * (probability - 0.5), 4)


def compare(result, sport, home, away, kickoff, league_id=None):
    """Add sportsbook evidence without mutating model output or changing rankings."""
    picks = result.get("picks") or []
    mapping = MARKETS.get(sport, {})
    market_keys = {mapping[pick["market"]] for pick in picks if pick.get("market") in mapping}
    feed = snapshot(sport, home, away, kickoff, market_keys, league_id) if picks else {"status": "no_picks", "quotes": []}
    counts = Counter(_name(pick.get("name")) for pick in picks)
    enriched, matched = [], 0
    for pick in picks:
        name, market = _name(pick.get("name")), mapping.get(pick.get("market"))
        reference = _number(pick.get("line"))
        matches = [quote for quote in feed["quotes"] if counts[name] == 1 and quote["player"] == name
                   and quote["market"] == market and pick.get("side") in {"over", "under"} and reference is not None]
        comparisons = []
        for book in BOOKS:
            options = [quote for quote in matches if quote["bookmaker_key"] == book]
            if not options:
                continue
            quote = min(options, key=lambda item: (abs(item["line"] - reference), item["line"]))
            selected = quote[f'{pick["side"]}_decimal']
            implied = 1 / selected
            total = 1 / quote["over_decimal"] + 1 / quote["under_decimal"]
            comparisons.append({**{key: value for key, value in quote.items() if key not in {"player", "over_decimal", "under_decimal"}},
                                "side": pick["side"], "decimal_odds": selected, "implied_probability": round(implied, 4),
                                "fair_probability": round(implied / total, 4) if quote["line"] % 1 == 0.5 else None,
                                "model_chance": _model_at_line(pick, quote["line"]),
                                "source": "The Odds API"})
        matched += bool(comparisons)
        enriched.append({**pick, "line_source": "historical", "sportsbook_quotes": comparisons})
    status = feed["status"] if not feed["quotes"] or matched else "no_quotes"
    return {**result, "picks": enriched, "sportsbook": {
        "status": status, "provider": "The Odds API", "matched_picks": matched, "total_picks": len(picks),
        "reason": MESSAGES.get(status, f"{matched} of {len(picks)} props matched to fresh sportsbook lines."),
        "validation": "Market comparisons are experimental; accuracy at sportsbook lines is not established.",
    }}
