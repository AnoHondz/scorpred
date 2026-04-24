from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class DecisionEngine:
    """Centralized intelligence layer that builds canonical match decisions."""

    def build_decision(self, match_data: dict[str, Any]) -> dict[str, Any]:
        probabilities = self._extract_probabilities(match_data)
        side = self._pick_side(match_data, probabilities)
        confidence = self._confidence(match_data, probabilities, side)
        model_probability = round(max(0.0, min(1.0, confidence / 100.0)), 4)
        implied = self._implied_probability(match_data, side)
        edge_score = None if implied is None else round(model_probability - implied, 4)
        expected_value = None if implied is None else round(model_probability - implied, 4)
        data_quality = self._data_quality(match_data)
        risk_score = self._risk_score(confidence, data_quality, probabilities)
        risk_level = self._risk_level(risk_score)
        action = self._action(confidence, edge_score, risk_level, implied is None, data_quality)
        decision_grade = self._decision_grade(confidence, risk_score, edge_score, data_quality)
        reasoning = self._reasoning(match_data, side, confidence, data_quality)

        return {
            "side": side,
            "action": action,
            "confidence": confidence,
            "probabilities": probabilities,
            "model_probability": model_probability,
            "implied_probability": implied,
            "edge_score": edge_score,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "expected_value": expected_value,
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
        return {"home": round(home, 1), "draw": round(draw, 1), "away": round(away, 1)}

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

    def _implied_probability(self, match_data: dict[str, Any], side: str) -> float | None:
        odds = match_data.get("odds") or {}
        if not isinstance(odds, dict):
            raw = match_data.get("implied_probability")
            if raw in (None, ""):
                return None
            return max(0.01, min(0.99, float(raw)))
        side_key = "home"
        if side.lower() == "draw":
            side_key = "draw"
        elif side == match_data.get("away_name") or side.lower().startswith("away"):
            side_key = "away"
        odd = odds.get(side_key)
        try:
            odd_f = float(odd)
            if odd_f > 1.0:
                return max(0.01, min(0.99, 1.0 / odd_f))
        except (TypeError, ValueError):
            pass
        raw = match_data.get("implied_probability")
        if raw in (None, ""):
            return None
        return max(0.01, min(0.99, float(raw)))

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

    def _risk_score(self, confidence: int, data_quality: int, probabilities: dict[str, float]) -> float:
        spread = max(probabilities.values()) - min(probabilities.values())
        confidence_penalty = max(0.0, (65 - confidence) / 100.0)
        quality_penalty = max(0.0, (70 - data_quality) / 100.0)
        variance_penalty = max(0.0, (15 - spread) / 100.0)
        return round(min(1.0, confidence_penalty + quality_penalty + variance_penalty), 4)

    def _risk_level(self, risk_score: float) -> str:
        if risk_score >= 0.45:
            return "HIGH"
        if risk_score >= 0.2:
            return "MEDIUM"
        return "LOW"

    def _action(
        self,
        confidence: int,
        edge_score: float | None,
        risk_level: str,
        missing_market: bool,
        data_quality: int,
    ) -> str:
        if missing_market:
            if confidence >= 66 and data_quality >= 70 and risk_level != "HIGH":
                return "BET"
            if confidence >= 55:
                return "CONSIDER"
            return "SKIP"
        if confidence >= 64 and (edge_score or 0.0) >= 0.02 and risk_level != "HIGH":
            return "BET"
        if confidence >= 54 and (edge_score or 0.0) >= -0.01:
            return "CONSIDER"
        return "SKIP"

    def _decision_grade(
        self,
        confidence: int,
        risk_score: float,
        edge_score: float | None,
        data_quality: int,
    ) -> str:
        quality = confidence * 0.5 + data_quality * 0.3 + (1 - risk_score) * 100 * 0.2
        if edge_score is not None:
            quality += edge_score * 100 * 0.2
        if quality >= 82:
            return "A"
        if quality >= 72:
            return "B"
        if quality >= 60:
            return "C"
        return "D"

    def _reasoning(self, match_data: dict[str, Any], side: str, confidence: int, data_quality: int) -> dict[str, list[str]]:
        strengths = []
        risks = []

        for item in (match_data.get("strengths") or []):
            text = str(item).strip()
            if text:
                strengths.append(text)
        for item in (match_data.get("risks") or []):
            text = str(item).strip()
            if text:
                risks.append(text)

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

        if data_quality < 55:
            risks.append("Data quality is limited for this fixture")

        return {
            "strengths": strengths[:3],
            "risks": risks[:3],
        }
