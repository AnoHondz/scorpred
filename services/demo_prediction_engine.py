"""
DemoPredictionEngine — deterministic, API-free match predictions for demo mode.

Uses a seeded RNG (keyed on match_id + team names) so the same match always
produces identical probabilities regardless of when or how many times it runs.
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Any

# Known team strength estimates (0.0 – 1.0 scale)
_TEAM_STRENGTH: dict[str, float] = {
    "Manchester City": 0.95, "Real Madrid": 0.97, "Bayern Munich": 0.94,
    "Arsenal": 0.90, "Liverpool": 0.90, "PSG": 0.91,
    "Barcelona": 0.92, "Inter Milan": 0.88, "AC Milan": 0.86,
    "Chelsea": 0.83, "Atletico Madrid": 0.87, "Juventus": 0.84,
    "Tottenham Hotspur": 0.82, "Dortmund": 0.85, "Napoli": 0.82,
    "Manchester United": 0.80, "Leipzig": 0.82, "Benfica": 0.79,
    "Newcastle United": 0.78, "Marseille": 0.78, "Porto": 0.80,
    "Aston Villa": 0.77, "Monaco": 0.76, "Ajax": 0.75,
    "West Ham United": 0.72, "Feyenoord": 0.74,
    "Brighton": 0.71, "Brentford": 0.69, "PSV": 0.78,
    "Fulham": 0.68, "Wolves": 0.66, "Crystal Palace": 0.65,
    "Nottingham Forest": 0.64, "Everton": 0.62, "Bournemouth": 0.61,
    "Luton": 0.58, "Burnley": 0.57, "Sheffield United": 0.55,
}

_HOME_ADVANTAGE = 0.055
_DEFAULT_STRENGTH = 0.65
_DEFAULT_VOLATILITY = 0.09

# Leagues with more/less variance
_LEAGUE_VOLATILITY: dict[int, float] = {
    2: 0.12,   # Champions League
    3: 0.11,   # Europa League
    39: 0.08,  # Premier League
    140: 0.09, # La Liga
    78: 0.09,  # Bundesliga
    61: 0.10,  # Ligue 1
    135: 0.09, # Serie A
}


def _seed_for(match_id: str | int, home: str, away: str) -> int:
    raw = f"{match_id}:{home}:{away}".encode()
    return int(hashlib.sha256(raw).hexdigest(), 16) % (2 ** 32)


def _team_strength(name: str, rng: random.Random) -> float:
    known = _TEAM_STRENGTH.get(name)
    if known is not None:
        return known
    return max(0.45, min(0.88, _DEFAULT_STRENGTH + rng.uniform(-0.08, 0.08)))


def _probabilities(
    home_str: float,
    away_str: float,
    volatility: float,
    rng: random.Random,
) -> tuple[float, float, float]:
    """Return (home_pct, draw_pct, away_pct) summing to 100.0."""
    noise = rng.uniform(-volatility, volatility)
    gap = (home_str + _HOME_ADVANTAGE) - away_str + noise
    home_raw = 1.0 / (1.0 + math.exp(-gap * 8))
    draw_frac = max(0.08, min(0.32, 0.26 - abs(gap) * 0.35))
    remaining = 1.0 - draw_frac
    home_pct = round(home_raw * remaining * 100, 1)
    away_pct = round((1.0 - home_raw) * remaining * 100, 1)
    draw_pct = round(100.0 - home_pct - away_pct, 1)
    return home_pct, max(0.0, draw_pct), max(0.0, away_pct)


class DemoPredictionEngine:
    """Injects deterministic simulated predictions into fixture dicts in-place."""

    def inject(self, fixture: dict[str, Any]) -> None:
        fix_block = fixture.get("fixture") or {}
        teams = fixture.get("teams") or {}
        home_name = (teams.get("home") or {}).get("name") or "Home"
        away_name = (teams.get("away") or {}).get("name") or "Away"
        match_id = str(fix_block.get("id") or "")
        lid = int((fixture.get("league") or {}).get("id") or 39)

        rng = random.Random(_seed_for(match_id, home_name, away_name))
        volatility = _LEAGUE_VOLATILITY.get(lid, _DEFAULT_VOLATILITY)
        home_str = _team_strength(home_name, rng)
        away_str = _team_strength(away_name, rng)
        home_pct, draw_pct, away_pct = _probabilities(home_str, away_str, volatility, rng)

        max_pct = max(home_pct, away_pct, draw_pct)
        if home_pct >= away_pct and home_pct >= draw_pct:
            pick, pick_team = "Home Win", home_name
        elif away_pct >= home_pct and away_pct >= draw_pct:
            pick, pick_team = "Away Win", away_name
        else:
            pick, pick_team = "Draw", "Draw"

        if max_pct >= 55:
            confidence = round(min(85.0, 65.0 + (max_pct - 55) * 0.8), 1)
        elif max_pct >= 45:
            confidence = round(55.0 + (max_pct - 45) * 1.0, 1)
        else:
            confidence = round(48.0 + max_pct * 0.2, 1)

        fixture["prediction"] = {
            "win_probabilities": {"a": home_pct, "draw": draw_pct, "b": away_pct},
            "best_pick": {
                "prediction": pick,
                "team": pick_team,
                "confidence": confidence,
                "reasoning": (
                    f"Demo rules: {home_name} strength {home_str:.2f} vs "
                    f"{away_name} strength {away_str:.2f} (home advantage applied)."
                ),
            },
            "confidence_pct": confidence,
            "confidence": confidence,
            "prob_a": home_pct,
            "prob_draw": draw_pct,
            "prob_b": away_pct,
            "home_pct": home_pct,
            "draw_pct": draw_pct,
            "away_pct": away_pct,
            "data_completeness": {"tier": "demo"},
            "data_quality": "Demo",
            "prediction_source": "ScorPred demo rules",
            "winner_label": pick,
            "form_a": [],
            "form_b": [],
            "h2h_form_a": [],
            "h2h_form_b": [],
        }
