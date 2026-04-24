from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class DecisionEngine:
    """Centralized intelligence layer that builds canonical match decisions.

    Implements quant-style edge / expected value / risk scoring. Odds are never
    invented: when decimal odds for the recommended side are missing, the
    edge_score and expected_value fields are returned as ``None`` and the
    decision falls back to confidence + data quality.
    """

    def build_decision(self, match_data: dict[str, Any]) -> dict[str, Any]:
        probabilities = self._extract_probabilities(match_data)
        side = self._pick_side(match_data, probabilities)
        confidence = self._confidence(match_data, probabilities, side)
        data_quality = self._data_quality(match_data)
        data_label = self._data_quality_label(data_quality, match_data)
        decimal_odds = self._side_decimal_odds(match_data, side)

        model_prob = max(0.0, min(1.0, confidence / 100.0))

        if decimal_odds is not None:
            implied_probability = round(1.0 / decimal_odds, 4)
            edge_score = round(model_prob - implied_probability, 4)
            expected_value = round(
                (model_prob * (decimal_odds - 1.0)) - (1.0 - model_prob), 4
            )
        else:
            implied_probability = None
            edge_score = None
            expected_value = None

        metric_breakdown = match_data.get("metric_breakdown")
        match_status = str(match_data.get("status") or "").strip().lower()

        risk_score = self._risk_score(
            confidence=confidence,
            data_label=data_label,
            edge_score=edge_score,
            metric_breakdown=metric_breakdown,
            match_status=match_status,
        )
        risk_level = self._risk_level(risk_score)
        action = self._action(
            confidence=confidence,
            edge_score=edge_score,
            expected_value=expected_value,
            data_label=data_label,
        )
        decision_grade = self._decision_grade(
            action=action,
            edge_score=edge_score,
            expected_value=expected_value,
            risk_level=risk_level,
        )
        reasoning = self._reasoning(
            match_data=match_data,
            side=side,
            confidence=confidence,
            data_label=data_label,
            edge_score=edge_score,
            metric_breakdown=metric_breakdown,
            decimal_odds=decimal_odds,
            risk_level=risk_level,
        )

        return {
            "side": side,
            "action": action,
            "confidence": confidence,
            "model_probability": round(model_prob, 4),
            "probabilities": probabilities,
            "implied_probability": implied_probability,
            "edge_score": edge_score,
            "expected_value": expected_value,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "decision_grade": decision_grade,
            "data_quality": data_quality,
            "reasoning": reasoning,
        }

    def _extract_probabilities(self, match_data: dict[str, Any]) -> dict[str, float]:
        raw = match_data.get("probabilities") or match_data.get("win_probabilities") or {}
        home = float(raw.get("home", raw.get("a", 0.0)) or 0.0)
        draw = float(raw.get("draw", 0.0) or 0.0)
        away = float(raw.get("away", raw.get("b", 0.0)) or 0.0)
        total = home + draw + away
        if total <= 0:
            home, draw, away = 34.0, 32.0, 34.0
            total = 100.0
        if abs(total - 100.0) > 0.01:
            scale = 100.0 / total
            home, draw, away = home * scale, draw * scale, away * scale
        return {
            "home": round(home, 1),
            "draw": round(draw, 1),
            "away": round(away, 1),
        }

    def _pick_side(self, match_data: dict[str, Any], probabilities: dict[str, float]) -> str:
        explicit = str(match_data.get("recommended_side") or match_data.get("side") or "").strip()
        if explicit:
            return explicit
        mapping = {
            "home": match_data.get("home_name") or "Home",
            "draw": "Draw",
            "away": match_data.get("away_name") or "Away",
        }
        key = max(probabilities, key=probabilities.get)
        return str(mapping.get(key) or "Home")

    def _confidence(self, match_data: dict[str, Any], probabilities: dict[str, float], side: str) -> int:
        raw_conf = match_data.get("confidence") or match_data.get("confidence_pct")
        if raw_conf is not None:
            return int(max(0, min(100, round(float(raw_conf)))))
        side_key = "home" if side == match_data.get("home_name") else "away"
        if side.lower() == "draw":
            side_key = "draw"
        return int(max(0, min(100, round(probabilities.get(side_key, max(probabilities.values()))))))

    def _side_decimal_odds(self, match_data: dict[str, Any], side: str) -> float | None:
        explicit = match_data.get("decimal_odds")
        if explicit is not None:
            try:
                value = float(explicit)
                if value > 1.0:
                    return value
            except (TypeError, ValueError):
                pass

        odds = match_data.get("odds")
        if not isinstance(odds, dict):
            return None

        side_key = "home"
        if side.lower() == "draw":
            side_key = "draw"
        elif side == match_data.get("away_name") or side.lower().startswith("away"):
            side_key = "away"

        candidate = odds.get(side_key)
        if candidate is None and side_key == "home":
            candidate = odds.get("a")
        if candidate is None and side_key == "away":
            candidate = odds.get("b")

        try:
            value = float(candidate)
            if value > 1.0:
                return value
        except (TypeError, ValueError):
            return None
        return None

    def _data_quality(self, match_data: dict[str, Any]) -> int:
        raw = match_data.get("data_quality")
        if isinstance(raw, (int, float)):
            return int(max(0, min(100, round(float(raw)))))
        tier = str((match_data.get("data_completeness") or {}).get("tier") or raw or "partial").lower()
        if "strong" in tier:
            return 85
        if "limited" in tier or "low" in tier:
            return 45
        return 65

    @staticmethod
    def _data_quality_label(score: int, match_data: dict[str, Any]) -> str:
        raw = match_data.get("data_quality")
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if "strong" in normalized:
                return "Strong Data"
            if "partial" in normalized or "moderate" in normalized or "mixed" in normalized:
                return "Partial Data"
            if "limited" in normalized or "weak" in normalized or "low" in normalized:
                return "Limited Data"
        if score >= 75:
            return "Strong Data"
        if score >= 55:
            return "Partial Data"
        return "Limited Data"

    def _risk_score(
        self,
        *,
        confidence: int,
        data_label: str,
        edge_score: float | None,
        metric_breakdown: Any,
        match_status: str,
    ) -> int:
        risk = 100 - int(confidence)
        if data_label != "Strong Data":
            risk += 10
        if edge_score is not None and edge_score < 0.05:
            risk += 10
        if metric_breakdown in (None, "Unavailable") or (
            isinstance(metric_breakdown, dict) and not metric_breakdown
        ):
            risk += 10
        if match_status in {"live", "", "unknown"}:
            risk += 10
        return max(0, min(100, risk))

    @staticmethod
    def _risk_level(risk_score: int) -> str:
        if risk_score <= 30:
            return "LOW"
        if risk_score <= 55:
            return "MEDIUM"
        return "HIGH"

    @staticmethod
    def _action(
        *,
        confidence: int,
        edge_score: float | None,
        expected_value: float | None,
        data_label: str,
    ) -> str:
        if edge_score is not None and expected_value is not None:
            if edge_score >= 0.08 and expected_value >= 0.05 and confidence >= 65:
                return "BET"
            if edge_score >= 0.03 and confidence >= 55:
                return "CONSIDER"
            return "SKIP"
        if confidence >= 65 and data_label in {"Strong Data", "Partial Data"}:
            return "BET"
        if confidence >= 55:
            return "CONSIDER"
        return "SKIP"

    @staticmethod
    def _decision_grade(
        *,
        action: str,
        edge_score: float | None,
        expected_value: float | None,
        risk_level: str,
    ) -> str:
        if (
            expected_value is not None
            and edge_score is not None
            and expected_value >= 0.15
            and edge_score >= 0.10
            and risk_level == "LOW"
        ):
            return "A+"
        if (
            expected_value is not None
            and edge_score is not None
            and expected_value >= 0.10
            and edge_score >= 0.08
        ):
            return "A"
        if action == "BET":
            return "B"
        if action == "CONSIDER":
            return "C"
        return "D"

    def _reasoning(
        self,
        *,
        match_data: dict[str, Any],
        side: str,
        confidence: int,
        data_label: str,
        edge_score: float | None,
        metric_breakdown: Any,
        decimal_odds: float | None,
        risk_level: str,
    ) -> dict[str, list[str]]:
        strengths: list[str] = []
        risks: list[str] = []

        for item in (match_data.get("strengths") or []):
            text = str(item).strip()
            if text:
                strengths.append(text)
        for item in (match_data.get("risks") or []):
            text = str(item).strip()
            if text:
                risks.append(text)

        if edge_score is not None and edge_score > 0:
            strengths.append(f"Positive edge of {edge_score * 100:.1f}% vs market price")
        if confidence >= 65:
            strengths.append(f"Strong model confidence ({confidence}%) on {side}")
        if data_label == "Strong Data":
            strengths.append("Strong data quality supports the read")
        if isinstance(metric_breakdown, dict) and metric_breakdown:
            strengths.append("Favorable metric breakdown")

        if decimal_odds is None:
            risks.append("No market odds available — value cannot be priced")
        if data_label != "Strong Data":
            risks.append(f"Limited data quality ({data_label})")
        if risk_level == "HIGH":
            risks.append("High overall risk score on this fixture")
        if metric_breakdown in (None, "Unavailable") or (
            isinstance(metric_breakdown, dict) and not metric_breakdown
        ):
            risks.append("Metric breakdown unavailable")

        if not strengths:
            strengths = [
                f"Model probabilities favor {side}",
                f"Confidence signal is {confidence}%",
            ]
        if not risks:
            risks = [
                "Line movement can reduce edge before kickoff",
                "Late squad news may change expected outcome",
            ]

        return {
            "strengths": _dedupe(strengths)[:4],
            "risks": _dedupe(risks)[:4],
        }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
