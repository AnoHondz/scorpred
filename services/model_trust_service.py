from __future__ import annotations

from typing import Any


def compute_trust_value(
    *,
    calibration_score: float | None,
    recent_accuracy: float | None,
    average_data_quality: float | None,
    sample_size: int,
    min_samples: int = 5,
) -> float | None:
    if sample_size < min_samples:
        return None

    cal = _as_percent(calibration_score) or 0.0
    acc = _as_percent(recent_accuracy) or 0.0
    dq = _as_percent(average_data_quality) or 0.0
    sample_size_score = min(100.0, float(sample_size))

    trust_score = cal * 0.45 + acc * 0.30 + dq * 0.10 + sample_size_score * 0.15
    return round(max(0.0, min(100.0, trust_score)), 1)


def compute_trust_score(
    *,
    calibration_score: float | None,
    recent_accuracy: float | None,
    average_data_quality: float | None,
    sample_size: int,
) -> dict[str, Any]:
    trust_score = compute_trust_value(
        calibration_score=calibration_score,
        recent_accuracy=recent_accuracy,
        average_data_quality=average_data_quality,
        sample_size=sample_size,
        min_samples=5,
    )
    if trust_score is None:
        return {
            "trust_score": None,
            "label": "Insufficient Data",
            "sample_size": sample_size,
        }
    if trust_score >= 85:
        label = "Elite Trust"
    elif trust_score >= 70:
        label = "Strong Trust"
    elif trust_score >= 55:
        label = "Developing Trust"
    else:
        label = "Low Trust"
    return {
        "trust_score": round(trust_score, 1),
        "label": label,
        "sample_size": sample_size,
    }


def _as_percent(value: Any) -> float | None:
    try:
        if value is None:
            return None
        val = float(value)
        if 0.0 <= val <= 1.0:
            return val * 100.0
        return val
    except (TypeError, ValueError):
        return None
