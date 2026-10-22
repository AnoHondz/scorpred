"""Verified track record for published rule-engine picks, plus the soccer market benchmark.

Only picks first recorded before a known kickoff are counted. Late or unverifiable
records are reported as exclusions rather than silently dropped.
"""
from __future__ import annotations

import json
import math
from typing import Any

import model_tracker as mt
from runtime_paths import repo_root

MINIMUM_SAMPLE = 100
NBA_REGULAR_SEASON = 2
_MARKET_REPORT = repo_root() / "data" / "validation" / "market_evaluation.json"


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> list[float] | None:
    if trials <= 0:
        return None
    phat = successes / trials
    denominator = 1 + z * z / trials
    centre = (phat + z * z / (2 * trials)) / denominator
    spread = z * math.sqrt(phat * (1 - phat) / trials + z * z / (4 * trials * trials)) / denominator
    return [round(max(0.0, centre - spread), 4), round(min(1.0, centre + spread), 4)]


def _sport_summary(records: list[dict], sport: str) -> dict[str, Any]:
    rows = [r for r in records if str(r.get("sport", "")).lower() == sport]
    verified = [r for r in rows if mt.verified_pregame(r)]
    excluded_late = sum(1 for r in rows if r.get("kickoff_at") and not mt.verified_pregame(r))
    excluded_unverifiable = sum(1 for r in rows if not r.get("kickoff_at"))
    excluded_preseason = 0
    if sport == "nba":
        excluded_preseason = sum(1 for r in verified if r.get("season_type") not in (None, NBA_REGULAR_SEASON))
        verified = [r for r in verified if r.get("season_type") in (None, NBA_REGULAR_SEASON)]
    graded = [r for r in verified if r.get("status") == "completed" and r.get("is_correct") is not None]
    correct = sum(1 for r in graded if r.get("is_correct"))
    accuracy = round(correct / len(graded), 4) if graded else None
    return {
        "graded": len(graded),
        "correct": correct,
        "accuracy": accuracy,
        "accuracy_95ci": wilson_interval(correct, len(graded)),
        "pending": sum(1 for r in verified if r.get("status") != "completed"),
        "excluded": {"recorded_after_kickoff": excluded_late, "no_kickoff_time": excluded_unverifiable,
                     "preseason": excluded_preseason},
        "sample_status": "sufficient" if len(graded) >= MINIMUM_SAMPLE else "insufficient",
        "first_kickoff": min((r["kickoff_at"] for r in graded), default=None),
        "last_kickoff": max((r["kickoff_at"] for r in graded), default=None),
    }


def _market_benchmark() -> dict[str, Any] | None:
    try:
        report = json.loads(_MARKET_REPORT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    early = report["betting"]["average_early"]
    return {
        "generated_at": report["generated_at"],
        "test_window": report["test_window"],
        "matches": report["matching"]["evaluated_with_complete_prices"],
        "model_accuracy": report["model"]["accuracy"],
        "market_accuracy": report["market"]["accuracy"],
        "log_loss_gap": report["model_minus_market_log_loss"]["mean"],
        "log_loss_gap_95ci": report["model_minus_market_log_loss"]["95ci"],
        "model_pick_roi": early["model_top_pick"]["roi"],
        "model_pick_roi_95ci": early["model_top_pick"]["roi_95ci"],
        "value_bet_roi": early["value_edge_over_5pct"]["roi"],
        "value_bet_roi_95ci": early["value_edge_over_5pct"]["roi_95ci"],
        "value_bets": early["value_edge_over_5pct"]["bets"],
        "model_predicted_draws": report["model_predicted_draws"],
    }


def summary() -> dict[str, Any]:
    records = mt._load_predictions()
    return {
        "minimum_sample": MINIMUM_SAMPLE,
        "sports": {sport: _sport_summary(records, sport) for sport in ("soccer", "nba")},
        "market_benchmark": _market_benchmark(),
        "notes": [
            "Counts only winner picks first recorded before the scheduled kickoff.",
            "Records from earlier rule versions are included when they meet that test.",
            "Intervals are 95% Wilson intervals; small samples cannot establish accuracy.",
        ],
    }
