"""Calibration tracking for ScorPred.

A calibrated model's stated confidence should match its empirical win rate:
if we say 70% 100 times, we should win ~70 of those. This service groups
completed predictions into confidence buckets, computes the actual win rate
per bucket, and returns an overall calibration error.

Only evaluated (completed) predictions count. Open / pending / pushed matches
are ignored. When there is not enough data, the service returns ``None``
rather than a fabricated score.
"""

from __future__ import annotations

from typing import Any, Iterable

_BUCKET_WIDTH = 10
_MIN_BUCKET_SIZE = 1


def _is_completed(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status not in {"completed", "evaluated"}:
        return False
    # push / draw outcomes don't contribute to win/loss calibration.
    if row.get("is_correct") is None:
        return False
    return True


def _confidence_value(row: dict[str, Any]) -> float | None:
    for key in ("confidence_pct", "confidence", "model_confidence"):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= value <= 1:
            value *= 100.0
        if 0 <= value <= 100:
            return value
    return None


def _bucket_key(confidence: float) -> tuple[int, int]:
    lower = int((confidence // _BUCKET_WIDTH) * _BUCKET_WIDTH)
    lower = max(0, min(100 - _BUCKET_WIDTH, lower))
    return lower, lower + _BUCKET_WIDTH


def get_calibration(bets: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return calibration rows keyed by 10%-wide confidence buckets.

    Each row exposes ``bucket`` (e.g. ``"60-70"``), ``sample_size``,
    ``predicted`` (mean confidence of that bucket), ``actual`` (empirical
    win rate) and ``error`` (absolute gap).
    """
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in bets or []:
        if not _is_completed(row):
            continue
        confidence = _confidence_value(row)
        if confidence is None:
            continue
        buckets.setdefault(_bucket_key(confidence), []).append(
            {"confidence": confidence, "is_correct": bool(row.get("is_correct"))}
        )

    rows: list[dict[str, Any]] = []
    for (low, high), entries in sorted(buckets.items()):
        if len(entries) < _MIN_BUCKET_SIZE:
            continue
        predicted = sum(e["confidence"] for e in entries) / len(entries)
        wins = sum(1 for e in entries if e["is_correct"])
        actual = (wins / len(entries)) * 100.0
        rows.append(
            {
                "bucket": f"{low}-{high}",
                "sample_size": len(entries),
                "predicted": round(predicted, 1),
                "actual": round(actual, 1),
                "error": round(abs(predicted - actual), 1),
            }
        )
    return rows


def calibration_score(bets: Iterable[dict[str, Any]]) -> float | None:
    """Return 0..1 calibration score: 1.0 = perfect, 0.0 = worst.

    Computed as ``1 - mean_absolute_error / 100`` across all populated
    buckets. Returns ``None`` when there is no completed data to score so
    callers can render "No data available" rather than a fake number.
    """
    rows = get_calibration(bets)
    if not rows:
        return None
    total_samples = sum(row["sample_size"] for row in rows)
    if total_samples == 0:
        return None
    weighted_error = sum(row["error"] * row["sample_size"] for row in rows)
    mae = weighted_error / total_samples
    return round(max(0.0, 1.0 - mae / 100.0), 4)
