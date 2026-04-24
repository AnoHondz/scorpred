"""Model Trust Score for ScorPred.

Blends calibration, recent accuracy, data quality, and sample size into a
single 0..100 trust score so the UI can say "Strong Trust" instead of just
showing raw confidence.

Only evaluated predictions contribute. With fewer than ``_MIN_SAMPLE_SIZE``
completed matches the service returns ``{"label": "Insufficient Data"}``
rather than faking confidence.
"""

from __future__ import annotations

from typing import Any, Iterable

from services.calibration_service import calibration_score

_MIN_SAMPLE_SIZE = 5
_RECENT_WINDOW = 20


def _is_completed(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status not in {"completed", "evaluated"}:
        return False
    return row.get("is_correct") is not None


def _recent_accuracy(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    recent = rows[-_RECENT_WINDOW:]
    wins = sum(1 for row in recent if row.get("is_correct") is True)
    return wins / len(recent)


def _data_quality_component(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    total = 0.0
    for row in rows:
        raw = row.get("data_quality")
        if isinstance(raw, (int, float)):
            total += max(0.0, min(1.0, float(raw) / 100.0))
        else:
            label = str(raw or "").strip().lower()
            if "strong" in label:
                total += 1.0
            elif "partial" in label or "moderate" in label:
                total += 0.6
            elif "limited" in label or "weak" in label or "low" in label:
                total += 0.3
            else:
                total += 0.5
    return total / len(rows)


def _sample_size_component(sample_size: int) -> float:
    # Logistic ramp: 0 completed → 0.0, 20+ completed → ~1.0.
    if sample_size <= 0:
        return 0.0
    return min(1.0, sample_size / 20.0)


def _label(score: float) -> str:
    if score >= 85:
        return "Elite Trust"
    if score >= 70:
        return "Strong Trust"
    if score >= 55:
        return "Developing Trust"
    return "Low Trust"


def compute_trust_score(bets: Iterable[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in (bets or []) if _is_completed(row)]
    sample_size = len(completed)
    if sample_size < _MIN_SAMPLE_SIZE:
        return {
            "score": None,
            "label": "Insufficient Data",
            "sample_size": sample_size,
            "components": {
                "calibration": None,
                "recent_accuracy": None,
                "data_quality": None,
                "sample_size": _sample_size_component(sample_size),
            },
            "explanation": (
                "Based on completed predictions, calibration, recent accuracy, "
                "data quality, and sample size."
            ),
        }

    calibration = calibration_score(completed) or 0.0
    recent = _recent_accuracy(completed)
    data_quality = _data_quality_component(completed)
    sample_component = _sample_size_component(sample_size)

    score = (
        calibration * 0.35
        + recent * 0.30
        + data_quality * 0.20
        + sample_component * 0.15
    ) * 100.0
    score = round(max(0.0, min(100.0, score)), 1)

    return {
        "score": score,
        "label": _label(score),
        "sample_size": sample_size,
        "components": {
            "calibration": round(calibration, 4),
            "recent_accuracy": round(recent, 4),
            "data_quality": round(data_quality, 4),
            "sample_size": round(sample_component, 4),
        },
        "explanation": (
            "Based on completed predictions, calibration, recent accuracy, "
            "data quality, and sample size."
        ),
    }
