"""
Nightly grader: fills PropPick.actual_value, .hit, .loss_reason
for picks whose game has already been played.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

MARKET_STAT_MAP = {
    "points":    "PTS",
    "rebounds":  "REB",
    "assists":   "AST",
    "tpm":       "FG3M",
    "steals":    "STL",
    "blocks":    "BLK",
    "turnovers": "TOV",
    "pra":       None,   # computed below
}


def _stat_from_box(box: dict, market_key: str) -> float | None:
    """Extract the target stat value from a game-log entry."""
    mk = (market_key or "").lower()
    stat_key = MARKET_STAT_MAP.get(mk)
    if stat_key:
        v = box.get(stat_key)
        return float(v) if v is not None else None
    if mk == "pra":
        pts = box.get("PTS") or 0
        reb = box.get("REB") or 0
        ast = box.get("AST") or 0
        return float(pts) + float(reb) + float(ast)
    # Try direct key lookup (handles custom markets)
    v = box.get(market_key.upper())
    return float(v) if v is not None else None


def _classify_loss(pick, actual: float) -> str:
    """Return a reason code when a pick misses."""
    minutes = pick.actual_value  # re-use if set; otherwise estimate from box
    # Heuristic checks ordered by specificity
    blowout = (pick.blowout_risk or "NONE").upper()
    if blowout == "HIGH":
        return "blowout_garbage_time"
    avg_min = pick.avg_minutes or 25.0
    # We don't have live minutes here; use context fields stored on pick
    extra = pick.get_extra()
    game_minutes = extra.get("minutes_played")
    if game_minutes is not None and float(game_minutes) < 20:
        return "low_minutes_player"
    gap = abs(actual - pick.line)
    if pick.line > 0 and gap / pick.line > 0.4:
        return "cold_game_outlier"
    if pick.line > 0 and gap / pick.line > 0.15:
        return "mild_underperformance"
    return "line_too_aggressive"


def grade_pending_picks() -> tuple[int, int]:
    """
    Find PropPick rows from the last 3 days with hit=None and grade them.
    Returns (graded_count, failed_count).
    """
    from db_models import db, PropPick
    import nba_client as nc

    today = date.today()
    cutoff = (today - timedelta(days=3)).isoformat()

    pending = PropPick.query.filter(
        PropPick.hit.is_(None),
        PropPick.game_date >= cutoff,
        PropPick.sport == "nba",
    ).all()

    if not pending:
        logger.info("prop_grader: no pending picks to grade")
        return 0, 0

    graded = failed = 0
    for pick in pending:
        try:
            if not pick.player_id:
                logger.debug("prop_grader: skip pick %s — no player_id", pick.id)
                continue

            logs = nc.get_player_game_log(int(pick.player_id))
            if not logs:
                continue

            game_date = pick.game_date  # "YYYY-MM-DD"
            # Find box-score entry within 1 day of game_date
            box = None
            for entry in logs:
                entry_date = (entry.get("GAME_DATE") or "")[:10]
                if abs((date.fromisoformat(entry_date) - date.fromisoformat(game_date)).days) <= 1:
                    box = entry
                    break

            if not box:
                continue

            actual = _stat_from_box(box, pick.market or "")
            if actual is None:
                continue

            hit = actual >= pick.line
            loss_reason = None if hit else _classify_loss(pick, actual)

            # Persist minutes in extra blob for future loss classification
            minutes_played = box.get("MIN")
            if minutes_played:
                extra = pick.get_extra()
                extra["minutes_played"] = float(str(minutes_played).split(":")[0])
                pick.set_extra(extra)

            pick.actual_value = actual
            pick.hit = hit
            pick.loss_reason = loss_reason
            graded += 1

        except Exception as exc:
            logger.warning("prop_grader: failed to grade pick %s: %s", pick.id, exc)
            failed += 1

    db.session.commit()
    logger.info("prop_grader: graded=%d failed=%d", graded, failed)
    return graded, failed
