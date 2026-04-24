from __future__ import annotations

from services.calibration_service import calibration_score, get_calibration
from services.model_trust_service import compute_trust_score


def _evaluated(confidence: float, is_correct: bool, **extra):
    return {
        "status": "completed",
        "confidence_pct": confidence,
        "is_correct": is_correct,
        **extra,
    }


def _open(confidence: float):
    return {"status": "open", "confidence_pct": confidence, "is_correct": None}


def test_calibration_groups_by_ten_percent_buckets():
    bets = [
        _evaluated(62, True),
        _evaluated(64, False),
        _evaluated(67, True),
        _evaluated(72, True),
        _evaluated(78, True),
    ]
    rows = get_calibration(bets)
    buckets = {row["bucket"] for row in rows}
    assert buckets == {"60-70", "70-80"}
    sixty = next(row for row in rows if row["bucket"] == "60-70")
    assert sixty["sample_size"] == 3
    assert sixty["actual"] == round(2 / 3 * 100, 1)
    seventy = next(row for row in rows if row["bucket"] == "70-80")
    assert seventy["actual"] == 100.0


def test_calibration_ignores_open_and_pushed_matches():
    bets = [
        _evaluated(60, True),
        _evaluated(60, False),
        _open(60),
        {"status": "completed", "confidence_pct": 60, "is_correct": None},  # push
    ]
    rows = get_calibration(bets)
    row = next(row for row in rows if row["bucket"] == "60-70")
    assert row["sample_size"] == 2


def test_calibration_score_none_when_no_completed_data():
    assert calibration_score([_open(70)]) is None
    assert calibration_score([]) is None


def test_calibration_score_perfect_when_win_rate_matches_confidence():
    # 10 bets at 70% confidence with exactly 7 wins → perfect calibration.
    bets = [_evaluated(70, True) for _ in range(7)] + [_evaluated(70, False) for _ in range(3)]
    score = calibration_score(bets)
    assert score is not None
    assert score >= 0.99


def test_trust_score_insufficient_when_fewer_than_five_completed():
    bets = [_evaluated(70, True)] + [_open(70) for _ in range(10)]
    result = compute_trust_score(bets)
    assert result["label"] == "Insufficient Data"
    assert result["score"] is None


def test_trust_score_strong_when_performance_is_strong():
    # 20 bets at 70%, 14 wins → well-calibrated, decent sample.
    bets = [
        _evaluated(70, True, data_quality="Strong Data") for _ in range(14)
    ] + [
        _evaluated(70, False, data_quality="Strong Data") for _ in range(6)
    ]
    result = compute_trust_score(bets)
    assert result["score"] is not None
    assert result["label"] in {"Strong Trust", "Elite Trust"}
    assert result["sample_size"] == 20


def test_trust_score_lower_when_calibration_is_weak():
    strong = compute_trust_score(
        [_evaluated(70, True, data_quality="Strong Data") for _ in range(14)]
        + [_evaluated(70, False, data_quality="Strong Data") for _ in range(6)]
    )
    # Model says 70% but only wins 20% → calibration error is huge.
    weak = compute_trust_score(
        [_evaluated(70, True, data_quality="Strong Data") for _ in range(4)]
        + [_evaluated(70, False, data_quality="Strong Data") for _ in range(16)]
    )
    assert strong["score"] > weak["score"]
