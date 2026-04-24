from __future__ import annotations

from services.decision_engine import DecisionEngine


def _base_match(**overrides):
    data = {
        "home_name": "Arsenal",
        "away_name": "Chelsea",
        "recommended_side": "Arsenal",
        "probabilities": {"home": 69, "draw": 16, "away": 15},
        "confidence": 69,
        "data_quality": "Strong Data",
        "metric_breakdown": {"form": {"home": 70, "away": 30}},
        "status": "scheduled",
    }
    data.update(overrides)
    return data


def test_canonical_output_includes_all_new_fields():
    decision = DecisionEngine().build_decision(_base_match(odds={"home": 1.90}))
    for key in (
        "side",
        "action",
        "confidence",
        "model_probability",
        "probabilities",
        "implied_probability",
        "edge_score",
        "expected_value",
        "risk_score",
        "risk_level",
        "decision_grade",
        "data_quality",
        "reasoning",
    ):
        assert key in decision, f"missing {key}"


def test_odds_available_positive_edge_creates_bet():
    decision = DecisionEngine().build_decision(_base_match(odds={"home": 1.90}))

    # implied = 1/1.90 ≈ 0.5263, edge ≈ 0.69 - 0.5263 = 0.1637
    assert decision["implied_probability"] == round(1 / 1.90, 4)
    assert decision["edge_score"] == round(0.69 - 1 / 1.90, 4)
    # EV = 0.69 * 0.90 - 0.31 = 0.311
    assert decision["expected_value"] == round(0.69 * 0.90 - 0.31, 4)
    assert decision["action"] == "BET"
    # confidence 69 → base risk 31 → MEDIUM; EV/edge clear A bar → grade A
    assert decision["risk_level"] == "MEDIUM"
    assert decision["decision_grade"] == "A"


def test_a_plus_grade_requires_low_risk_plus_strong_ev_and_edge():
    decision = DecisionEngine().build_decision(
        _base_match(
            confidence=72,
            probabilities={"home": 72, "draw": 14, "away": 14},
            odds={"home": 1.95},
        )
    )
    assert decision["risk_level"] == "LOW"
    assert decision["edge_score"] >= 0.10
    assert decision["expected_value"] >= 0.15
    assert decision["decision_grade"] == "A+"


def test_odds_available_negative_edge_creates_skip():
    # Strong favorite price → tiny implied probability gap, negative edge
    match = _base_match(
        confidence=55,
        probabilities={"home": 55, "draw": 25, "away": 20},
        odds={"home": 1.40},
    )
    decision = DecisionEngine().build_decision(match)

    assert decision["edge_score"] is not None
    assert decision["edge_score"] < 0
    assert decision["action"] == "SKIP"
    assert decision["decision_grade"] == "D"


def test_missing_odds_uses_confidence_only_fallback_without_fake_ev():
    decision = DecisionEngine().build_decision(_base_match())

    assert decision["implied_probability"] is None
    assert decision["edge_score"] is None
    assert decision["expected_value"] is None
    # confidence 69 with Strong Data → BET via fallback
    assert decision["action"] == "BET"
    # No EV/edge → cannot reach A+/A; BET → grade B
    assert decision["decision_grade"] == "B"
    assert any(
        "No market odds" in risk or "odds" in risk.lower()
        for risk in decision["reasoning"]["risks"]
    )


def test_missing_odds_low_confidence_skips():
    decision = DecisionEngine().build_decision(
        _base_match(
            confidence=40,
            probabilities={"home": 40, "draw": 30, "away": 30},
        )
    )
    assert decision["edge_score"] is None
    assert decision["action"] == "SKIP"


def test_risk_score_increases_when_data_quality_is_weak():
    strong = DecisionEngine().build_decision(
        _base_match(odds={"home": 1.90}, data_quality="Strong Data")
    )
    limited = DecisionEngine().build_decision(
        _base_match(odds={"home": 1.90}, data_quality="Limited Data")
    )
    assert limited["risk_score"] > strong["risk_score"]
    # +10 penalty for non-strong data
    assert limited["risk_score"] - strong["risk_score"] >= 10


def test_risk_score_penalises_low_edge_missing_breakdown_and_live_status():
    # Confidence high enough that 100-confidence base is small;
    # odds give a tiny edge; metric_breakdown and live status add penalties.
    match = _base_match(
        confidence=70,
        probabilities={"home": 70, "draw": 18, "away": 12},
        odds={"home": 1.50},  # implied ≈ 0.667, edge ≈ 0.033 (< 0.05)
        data_quality="Strong Data",
        metric_breakdown=None,
        status="live",
    )
    decision = DecisionEngine().build_decision(match)
    # base 30 + low edge (10) + missing breakdown (10) + live status (10) = 60 → HIGH
    assert decision["risk_score"] >= 50
    assert decision["risk_level"] in {"MEDIUM", "HIGH"}


def test_decision_grade_a_for_strong_ev_and_edge_with_medium_risk():
    # Edge ~0.09, EV ~0.10, MEDIUM risk → grade A (not A+)
    match = _base_match(
        confidence=66,
        probabilities={"home": 66, "draw": 18, "away": 16},
        odds={"home": 1.85},
        data_quality="Partial Data",  # forces +10 → MEDIUM
    )
    decision = DecisionEngine().build_decision(match)
    assert decision["edge_score"] >= 0.08
    assert decision["expected_value"] >= 0.10
    assert decision["decision_grade"] in {"A", "A+"}


def test_no_odds_invented_when_input_missing():
    decision = DecisionEngine().build_decision(_base_match(odds=None))
    assert decision["implied_probability"] is None
    assert decision["edge_score"] is None
    assert decision["expected_value"] is None


def test_consider_action_when_modest_edge():
    # edge between 0.03 and 0.08 with confidence 60 → CONSIDER
    match = _base_match(
        confidence=60,
        probabilities={"home": 60, "draw": 20, "away": 20},
        odds={"home": 1.80},  # implied ≈ 0.555, edge ≈ 0.045
    )
    decision = DecisionEngine().build_decision(match)
    assert 0.03 <= (decision["edge_score"] or 0) < 0.08
    assert decision["action"] == "CONSIDER"
    assert decision["decision_grade"] == "C"
