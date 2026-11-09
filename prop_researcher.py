"""
prop_researcher.py — Deep analysis brain for NBA prop bets.

Produces structured research per pick matching this format:
  Player — Stat Line (odds) vs OPP
  • Minutes: last-5 recent, season avg
  • Form: X/Y season hit rate, A/B recent; avg STAT RPG
  • Matchup: OPP allows N STAT to POS (rank label)
  • H2H: career vs OPP summary
  • Context: injury boosts, back-to-back fatigue
  • Blowout: spread context
  Grade: A / A- / B+ / B / B- / C

Data sources (graceful fallback chain):
  1. nba_client.py (RapidAPI) — full per-game logs, H2H, injuries
  2. NBA S3 public bucket — today's scoreboard, schedule (back-to-back), player index
  3. Derived from props_engine samples already in memory
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── S3 public endpoints ────────────────────────────────────────────────────────

_S3_BASE = "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com"
_S3_SCOREBOARD = f"{_S3_BASE}/NBA/liveData/scoreboard/todaysScoreboard_00.json"
_S3_SCHEDULE   = f"{_S3_BASE}/NBA/staticData/scheduleLeagueV2.json"
_S3_PLAYER_IDX = f"{_S3_BASE}/NBA/staticData/playerIndex.json"

_RESEARCH_CACHE: dict[str, tuple[float, Any]] = {}  # in-memory TTL cache
_S3_TTL = 3600   # 1 hour for static data
_LIVE_TTL = 120  # 2 min for scoreboard


def _s3_fetch(url: str, ttl: int = _S3_TTL) -> Any | None:
    """Fetch JSON from S3 public bucket with in-memory TTL cache."""
    now = time.time()
    if url in _RESEARCH_CACHE:
        ts, data = _RESEARCH_CACHE[url]
        if now - ts < ttl:
            return data

    try:
        import requests
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        _RESEARCH_CACHE[url] = (now, data)
        return data
    except Exception as e:
        logger.debug("S3 fetch failed %s: %s", url, e)
        # Return stale if available
        if url in _RESEARCH_CACHE:
            return _RESEARCH_CACHE[url][1]
        return None


def _get_player_index() -> list[dict]:
    """Return parsed player rows from NBA playerIndex."""
    data = _s3_fetch(_S3_PLAYER_IDX)
    if not data:
        return []
    rs = (data.get("resultSets") or [{}])[0]
    headers = rs.get("headers", [])
    rows = rs.get("rowSet", [])
    return [dict(zip(headers, row)) for row in rows]


def _get_today_games_s3() -> list[dict]:
    """Return today's games from S3 scoreboard."""
    data = _s3_fetch(_S3_SCOREBOARD, ttl=_LIVE_TTL)
    if not data:
        return []
    return data.get("scoreboard", {}).get("games", [])


def _get_full_schedule() -> list[dict]:
    """Return flat list of all season game entries from S3 schedule."""
    data = _s3_fetch(_S3_SCHEDULE)
    if not data:
        return []
    game_dates = data.get("leagueSchedule", {}).get("gameDates", [])
    games = []
    for gd in game_dates:
        for g in gd.get("games", []):
            games.append(g)
    return games


# ── Back-to-back detection ─────────────────────────────────────────────────────

def _is_back_to_back(team_tricode: str, today_str: str, all_games: list[dict]) -> bool:
    """
    Return True if the team played a game yesterday.
    today_str: 'YYYY-MM-DD'
    """
    from datetime import datetime, timedelta
    today = datetime.strptime(today_str, "%Y-%m-%d")
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    for g in all_games:
        gdate = g.get("gameDateEst", "")[:10]
        if gdate != yesterday_str:
            continue
        away = g.get("awayTeam", {}).get("teamTricode", "")
        home = g.get("homeTeam", {}).get("teamTricode", "")
        if team_tricode in (away, home):
            # Check it was a finished game
            if g.get("gameStatus") == 3:
                return True
    return False


# ── Hit rate from game log ─────────────────────────────────────────────────────

_MARKET_KEY_MAP = {
    "points":    "points",
    "rebounds":  "rebounds",
    "assists":   "assists",
    "tpm":       "tpm",
    "steals":    "steals",
    "blocks":    "blocks",
    "turnovers": "turnovers",
    "pra":       "pra",
    "pa":        "pa",
    "ra":        "ra",
    "pr":        "pr",
}

_STAT_API_KEY = {
    "points":    "points",
    "rebounds":  "rebounds",
    "assists":   "assists",
    "tpm":       "tpm",
    "steals":    "steals",
    "blocks":    "blocks",
    "turnovers": "turnovers",
}


def _extract_stat(game_record: dict, market_key: str) -> float | None:
    """Pull stat value from an nba_client game record."""
    stats = (game_record.get("statistics") or [{}])[0]
    if market_key in ("pra", "pa", "ra", "pr"):
        p = stats.get("points")
        r = stats.get("rebounds")
        a = stats.get("assists")
        if market_key == "pra":
            if p is None and r is None and a is None:
                return None
            return float(p or 0) + float(r or 0) + float(a or 0)
        if market_key == "pa":
            if p is None and a is None:
                return None
            return float(p or 0) + float(a or 0)
        if market_key == "ra":
            if r is None and a is None:
                return None
            return float(r or 0) + float(a or 0)
        if market_key == "pr":
            if p is None and r is None:
                return None
            return float(p or 0) + float(r or 0)
    api_key = _STAT_API_KEY.get(market_key, market_key)
    val = stats.get(api_key)
    return float(val) if val is not None else None


def _minutes_from_record(game_record: dict) -> float:
    stats = (game_record.get("statistics") or [{}])[0]
    raw = stats.get("min", "0") or "0"
    if ":" in str(raw):
        parts = str(raw).split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except ValueError:
            return 0.0
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0


def _hit_rate(game_log: list[dict], market_key: str, line: float) -> dict:
    """
    Compute hit rate stats from a game log.
    Returns: {season_hits, season_total, recent_hits, recent_total,
              last5_values, season_avg, recent_avg, last5_minutes}
    """
    values = []
    minutes = []
    for g in game_log:
        v = _extract_stat(g, market_key)
        if v is None:
            continue
        values.append(v)
        minutes.append(_minutes_from_record(g))

    # Recent = last 5 appearances
    recent_vals = values[-5:] if len(values) >= 5 else values
    recent_mins = minutes[-5:] if len(minutes) >= 5 else minutes

    season_hits = sum(1 for v in values if v >= line)
    recent_hits = sum(1 for v in recent_vals if v >= line)

    return {
        "season_hits":   season_hits,
        "season_total":  len(values),
        "recent_hits":   recent_hits,
        "recent_total":  len(recent_vals),
        "season_avg":    round(sum(values) / len(values), 1) if values else None,
        "recent_avg":    round(sum(recent_vals) / len(recent_vals), 1) if recent_vals else None,
        "last5_values":  recent_vals,
        "last5_minutes": recent_mins,
    }


def _h2h_summary(vs_opponent: dict, market_key: str, line: float) -> dict:
    """
    Build H2H summary from nba_client vs_opponent data.
    Returns: {career_hits, career_total, career_values, label}
    """
    records = vs_opponent.get("records") or []
    values = []
    for r in records:
        v = _extract_stat(r, market_key)
        if v is not None:
            values.append(v)

    career_hits = sum(1 for v in values if v >= line)
    return {
        "career_hits":   career_hits,
        "career_total":  len(values),
        "career_values": values[-5:],  # show last 5
    }


# ── Injury boost detection ─────────────────────────────────────────────────────

_CENTER_KEYWORDS  = ["C", "center"]
_SF_KEYWORDS      = ["SF", "small forward", "forward"]
_PG_KEYWORDS      = ["PG", "point guard"]


def _injury_context(team_injuries: list[dict], player_position: str) -> str | None:
    """
    Look for key injured players (opposing team) that boost this player's prop.
    Returns a brief string if significant, else None.
    """
    if not team_injuries:
        return None

    out_players = []
    for inj in team_injuries[:10]:
        status = (inj.get("status") or "").upper()
        name = inj.get("player", {}).get("name") if isinstance(inj.get("player"), dict) else str(inj.get("player", ""))
        if "OUT" in status and name:
            out_players.append(name)

    if out_players:
        return f"{', '.join(out_players[:2])} OUT"
    return None


# ── Matchup grade (defense vs position) ───────────────────────────────────────

def _matchup_label_legacy(opponent_stats: dict, market_key: str) -> str | None:
    """Fallback: team-level opp stats from props_engine._fetch_nba_opponent_stats."""
    if not opponent_stats:
        return None
    stat_map = {
        "points":   ["points_allowed_pg", "opp_pts", "opp_ppg"],
        "rebounds": ["reb_allowed_pg", "opp_reb"],
        "assists":  ["ast_allowed_pg", "opp_ast"],
    }
    keys = stat_map.get(market_key, [])
    val = None
    for k in keys:
        if k in opponent_stats:
            val = opponent_stats[k]
            break
    if val is None:
        return None
    thresholds = {"points": (115, 108), "rebounds": (46, 42), "assists": (27, 23)}
    hi, lo = thresholds.get(market_key, (999, 0))
    if val >= hi:
        return f"favorable ({val:.1f} allowed/g)"
    elif val <= lo:
        return f"tough ({val:.1f} allowed/g)"
    else:
        return f"neutral ({val:.1f} allowed/g)"


def _matchup_label(opponent_team_id, player_position: str, market_key: str) -> str | None:
    """
    Defense-by-position: calls nba_client.get_defense_vs_position().
    Returns rank label string or None.
    """
    if not opponent_team_id:
        return None
    pos_map = {
        "PG": "G", "SG": "G", "G": "G",
        "SF": "F", "PF": "F", "F": "F",
        "C": "C",
    }
    pos = pos_map.get(str(player_position or "").upper().split("-")[0], "F")
    try:
        import nba_client as nc
        result = nc.get_defense_vs_position(
            opponent_team_id=int(opponent_team_id),
            position_filter=pos,
            market_key=market_key,
        )
        if result:
            return result["rank_label"]
    except Exception:
        pass
    return None


# ── Grade formula ──────────────────────────────────────────────────────────────

def _compute_grade(
    season_hit_rate: float,   # 0.0–1.0
    recent_hit_rate: float,   # 0.0–1.0
    h2h_hit_rate: float | None,
    blowout_risk: str,        # "HIGH"/"MEDIUM"/"NONE"
    is_back_to_back: bool,
    minutes_avg: float,
    line: float,
    season_avg: float | None,
    matchup_label: str | None,
) -> tuple[str, str]:
    """
    Return (letter_grade, reason_string).
    Grade scale: A (90+), A- (85+), B+ (80+), B (70+), B- (60+), C (50+), D (<50)
    """
    score = 0.0
    reasons = []

    # Season hit rate (max 40 pts)
    score += season_hit_rate * 40
    if season_hit_rate >= 0.80:
        reasons.append(f"{season_hit_rate:.0%} season hit rate")

    # Recent form (max 30 pts)
    score += recent_hit_rate * 30
    if recent_hit_rate >= 0.80:
        reasons.append(f"{recent_hit_rate:.0%} last 5")

    # H2H history (max 10 pts)
    if h2h_hit_rate is not None:
        score += h2h_hit_rate * 10
        if h2h_hit_rate < 0.40:
            reasons.append(f"weak H2H ({h2h_hit_rate:.0%})")

    # Season avg clearance vs line (max 10 pts)
    if season_avg is not None and line > 0:
        clearance = (season_avg - line) / max(line, 1)
        score += min(10, max(0, clearance * 20))

    # Deductions
    if blowout_risk == "HIGH":
        score -= 15
        reasons.append("HIGH blowout risk")
    elif blowout_risk == "MEDIUM":
        score -= 7
        reasons.append("blowout concern")

    if is_back_to_back:
        score -= 8
        reasons.append("back-to-back fatigue")

    if minutes_avg < 20:
        score -= 10
        reasons.append("low minutes (<20 MPG)")

    if matchup_label and "tough" in (matchup_label or "").lower():
        score -= 5
        reasons.append("tough matchup")
    elif matchup_label and "favorable" in (matchup_label or "").lower():
        score += 5

    # Convert to letter
    if score >= 90:
        grade = "A+"
    elif score >= 82:
        grade = "A"
    elif score >= 75:
        grade = "A-"
    elif score >= 68:
        grade = "B+"
    elif score >= 60:
        grade = "B"
    elif score >= 52:
        grade = "B-"
    elif score >= 44:
        grade = "C+"
    elif score >= 36:
        grade = "C"
    else:
        grade = "D"

    reason = " | ".join(reasons) if reasons else "mixed signals"
    return grade, reason


# ── Main research function ─────────────────────────────────────────────────────

def research_prop(
    player_name: str,
    player_tricode: str,     # e.g. "PHX"
    opponent_tricode: str,   # e.g. "SAS"
    market_key: str,         # e.g. "rebounds"
    line: float,
    odds: int | None,        # American odds e.g. -380
    game_log: list[dict],    # from nba_client
    vs_opponent: dict,       # from nba_client
    opponent_team_id=None,
    opponent_stats: dict | None = None,    # from props_engine (legacy fallback)
    team_injuries: list[dict] | None = None,
    player_position: str = "",
    blowout_risk: str = "NONE",
    blowout_info: dict | None = None,
    today_str: str | None = None,
) -> dict:
    """
    Build a complete research card for one prop leg.
    Returns a dict with all analysis fields plus a letter grade.
    """
    from datetime import date as _date

    today_str = today_str or _date.today().isoformat()
    market_label_map = {
        "points": "PTS", "rebounds": "REB", "assists": "AST",
        "tpm": "3PM", "steals": "STL", "blocks": "BLK",
        "turnovers": "TOV", "pra": "PRA",
        "pa": "P+A", "ra": "R+A", "pr": "P+R",
    }
    mabbr = market_label_map.get(market_key, market_key.upper())

    # Hit rate from season game log
    hr = _hit_rate(game_log, market_key, line)
    season_hit_pct = hr["season_hits"] / hr["season_total"] if hr["season_total"] else 0.0
    recent_hit_pct = hr["recent_hits"] / hr["recent_total"] if hr["recent_total"] else 0.0

    # H2H
    h2h = _h2h_summary(vs_opponent, market_key, line)
    h2h_pct = h2h["career_hits"] / h2h["career_total"] if h2h["career_total"] else None

    # Back-to-back
    all_schedule = _get_full_schedule()
    b2b = _is_back_to_back(player_tricode, today_str, all_schedule)

    # Minutes
    min_avg = None
    if hr["last5_minutes"]:
        min_avg = round(sum(hr["last5_minutes"]) / len(hr["last5_minutes"]), 1)

    team_injuries = team_injuries or []

    # Injury context
    inj_note = _injury_context(team_injuries, player_position)

    # Matchup label — try new positional method first, fall back to legacy
    matchup_note = _matchup_label(opponent_team_id, player_position, market_key)
    if not matchup_note and opponent_stats:
        matchup_note = _matchup_label_legacy(opponent_stats, market_key)

    # Grade
    grade, grade_reason = _compute_grade(
        season_hit_rate=season_hit_pct,
        recent_hit_rate=recent_hit_pct,
        h2h_hit_rate=h2h_pct,
        blowout_risk=blowout_risk,
        is_back_to_back=b2b,
        minutes_avg=min_avg or 25.0,
        line=line,
        season_avg=hr["season_avg"],
        matchup_label=matchup_note,
    )

    # Odds display
    odds_str = ""
    if odds is not None:
        odds_str = f" ({'+' if odds > 0 else ''}{odds})"

    # Build bullet-point analysis text
    bullets = []

    # Minutes bullet
    if hr["last5_minutes"]:
        min_strs = [str(int(m)) for m in hr["last5_minutes"]]
        bullets.append(f"Minutes: {', '.join(min_strs)} last 5"
                       + (f"; avg {min_avg}" if min_avg else ""))

    # Form bullet
    if hr["season_total"] > 0:
        form_parts = [
            f"{hr['season_hits']}/{hr['season_total']} this season",
        ]
        if hr["recent_total"] > 0:
            form_parts.append(f"{hr['recent_hits']}/{hr['recent_total']} recent")
        if hr["season_avg"] is not None:
            form_parts.append(f"avg {hr['season_avg']} {mabbr}/g")
        if hr["recent_avg"] is not None and hr["recent_avg"] != hr["season_avg"]:
            form_parts.append(f"({hr['recent_avg']} last 5)")
        bullets.append("Form: " + ", ".join(form_parts))

    # Matchup bullet
    if matchup_note:
        bullets.append(f"Matchup: {opponent_tricode} defense is {matchup_note} for {mabbr}")

    # H2H bullet
    if h2h["career_total"] > 0:
        vals_str = ", ".join(str(int(v)) for v in h2h["career_values"])
        h2h_rate_str = f"{h2h['career_hits']}/{h2h['career_total']} hit"
        bullets.append(f"H2H vs {opponent_tricode}: {vals_str} — {h2h_rate_str}")

    # Injury bullet
    if inj_note:
        bullets.append(f"Injury boost: {inj_note}")

    # Back-to-back bullet
    if b2b:
        bullets.append(f"Back-to-back: played yesterday — fatigue risk")

    # Blowout bullet
    if blowout_info:
        spread = blowout_info.get("spread")
        prob = blowout_info.get("blowout_prob", 0)
        risk_level = blowout_info.get("risk", "NONE")
        if spread is not None:
            bullets.append(f"Blowout risk: {risk_level} (spread {spread:+.1f}, {prob:.0%} blowout prob)")
        elif risk_level != "NONE":
            bullets.append(f"Blowout risk: {risk_level} ({prob:.0%} probability)")

    return {
        "player":        player_name,
        "market":        market_key,
        "market_abbr":   mabbr,
        "line":          line,
        "odds":          odds,
        "odds_str":      odds_str,
        "opponent":      opponent_tricode,
        "headline":      f"{player_name} — {line}+ {mabbr}{odds_str} vs {opponent_tricode}",
        "bullets":       bullets,
        "grade":         grade,
        "grade_reason":  grade_reason,
        "hit_rate": {
            "season": f"{hr['season_hits']}/{hr['season_total']}",
            "recent": f"{hr['recent_hits']}/{hr['recent_total']}",
            "season_pct": round(season_hit_pct * 100, 1),
            "recent_pct": round(recent_hit_pct * 100, 1),
        },
        "h2h": {
            "rate":   f"{h2h['career_hits']}/{h2h['career_total']}",
            "values": h2h["career_values"],
        },
        "back_to_back":  b2b,
        "avg_minutes":   min_avg,
        "injury_note":   inj_note,
        "matchup_note":  matchup_note,
        "blowout_risk":  blowout_risk,
    }


def rank_props(research_cards: list[dict]) -> list[dict]:
    """
    Sort prop research cards by grade (best first).
    Returns cards with rank field added.
    """
    grade_order = {"A+": 10, "A": 9, "A-": 8, "B+": 7, "B": 6, "B-": 5,
                   "C+": 4, "C": 3, "D": 1}

    sorted_cards = sorted(
        research_cards,
        key=lambda c: grade_order.get(c.get("grade", "C"), 3),
        reverse=True
    )
    for i, card in enumerate(sorted_cards):
        card["rank"] = i + 1
    return sorted_cards


def build_research_summary(research_cards: list[dict]) -> str:
    """
    Build a human-readable ranking summary string.
    """
    lines = ["**Research Ranking**"]
    for card in research_cards:
        rank = card.get("rank", "?")
        player = card["player"]
        line = card["line"]
        mabbr = card["market_abbr"]
        grade = card["grade"]
        odds_str = card.get("odds_str", "")
        lines.append(f"{rank}. {player} {line}+ {mabbr}{odds_str} — {grade}")

    return "\n".join(lines)
