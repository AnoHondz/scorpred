"""Soccer player props: five best picks per match from ESPN box scores (services.prop_model).

Markets: shots, shots on target, goals, assists, fouls committed and goalkeeper saves,
for every league with an ESPN slug. History is this season and last (ESPN soccer seasons
are starting years). ESPN has no tackles; Premier League tackles come from
services.fpl_props. Premier League picks skip players Fantasy Premier League lists as
injured, doubtful or suspended; other leagues have no injury feed here.
"""
from api_client import ESPN_SLUG_BY_LEAGUE
from services import espn_box_scores as box
from services import prop_model


def position(raw):
    text = (raw or "").upper()
    if text.startswith("G"):
        return "G"
    if text.startswith(("CD", "CB", "LB", "RB", "LWB", "RWB", "SW")) or text == "D":
        return "D"
    if "M" in text:
        return "M"
    return "F"


OUTFIELD = {"D", "M", "F"}
CONFIG = {
    "markets": {"shots": (("shots",), 0.25), "shots_on_target": (("shots_on_target",), 0.30),
                "goals": (("goals",), 0.10), "assists": (("assists",), 0.10), "fouls": (("fouls",), 0.15),
                "saves": (("saves",), 0.10)},
    "labels": {"shots": "Shots", "shots_on_target": "Shots on target", "goals": "Goals", "assists": "Assists",
               "fouls": "Fouls committed", "saves": "Goalkeeper saves"},
    "position_markets": {"saves": {"G"}, "shots": OUTFIELD, "shots_on_target": OUTFIELD, "goals": OUTFIELD,
                         "assists": OUTFIELD, "fouls": OUTFIELD},
    "position": position, "prior_minutes": 270.0, "min_games": 4, "min_minutes": 60.0,
    # scripts/backtest_box_props.py soccer 2025 eng.1 (380 matches, 5,800 player-matches):
    # every market's chosen-side chance within 1.1 points of its hit rate and a lower Brier
    # score than the player's own record. Picks said 76.1%/77.3% and hit 79.2%/78.7% in the
    # first/second half, so no shrink. Saves picks are unstable (70% then 32% of 22): not
    # picked. Goals and assists are picked on the over side only: books barely post "no goal".
    "pick_markets": {"shots": 0.5, "shots_on_target": 0.5, "goals": 0.5, "assists": 0.5, "fouls": 0.5},
    "pick_sides": {"goals": {"over"}, "assists": {"over"}},
    "shrink": 1.0,
}


def season_of(kickoff):
    """ESPN soccer season id: the year a season starts (July onward)."""
    return kickoff.year if kickoff.month >= 7 else kickoff.year - 1


def slug_for(league_id):
    slug = ESPN_SLUG_BY_LEAGUE.get(int(league_id))
    if not slug:
        raise ValueError("This competition has no ESPN box scores.")
    return slug


def project(league_id, home_id, away_id, kickoff, excluded=frozenset()):
    slug, season = slug_for(league_id), season_of(kickoff)
    games = {}
    for team_id in (home_id, away_id):
        for game in box.team_games("soccer", team_id, (season - 1, season), league=slug, before=kickoff):
            games[game["id"]] = game
    return prop_model.game_props(CONFIG, home_id, away_id, list(games.values()), excluded)
