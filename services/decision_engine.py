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
        implied = self._implied_probability(match_data, side)
        edge_score = round((confidence / 100.0 - implied) * 100, 2)
        expected_value = round((confidence / 100.0 - implied) * 100, 2)
        data_quality = self._data_quality(match_data)
        risk_level = self._risk_level(confidence, data_quality, probabilities)
        action = self._action(confidence, edge_score, risk_level)
        reasoning = self._reasoning(match_data, side, confidence, data_quality)

        return {
            "side": side,
            "action": action,
            "confidence": confidence,
            "probabilities": probabilities,
            "edge_score": edge_score,
            "risk_level": risk_level,
            "expected_value": expected_value,
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

    def _implied_probability(self, match_data: dict[str, Any], side: str) -> float:
        odds = match_data.get("odds") or {}
        if not isinstance(odds, dict):
            return max(0.01, min(0.99, float(match_data.get("implied_probability") or 0.5)))
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
        return max(0.01, min(0.99, float(match_data.get("implied_probability") or 0.5)))

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

    def _risk_level(self, confidence: int, data_quality: int, probabilities: dict[str, float]) -> str:
        spread = max(probabilities.values()) - min(probabilities.values())
        if data_quality < 50 or confidence < 52 or spread < 8:
            return "HIGH"
        if confidence >= 65 and data_quality >= 70 and spread >= 15:
            return "LOW"
        return "MEDIUM"

    def _action(self, confidence: int, edge_score: float, risk_level: str) -> str:
        if confidence >= 64 and edge_score >= 2 and risk_level != "HIGH":
            return "BET"
        if confidence >= 54 and edge_score >= -1:
            return "CONSIDER"
        return "SKIP"

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
