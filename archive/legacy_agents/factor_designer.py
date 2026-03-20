"""
llm_agents/factor_designer.py
-----------------------------
Factor Designer Agent: converts strategy ideas into concrete signal rules,
thresholds, and filters expressed as StrategySpec components.

Input:  strategy idea from Researcher
Output: signal_rules, filters (structured for StrategySpec)
"""
from __future__ import annotations

import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a quantitative factor designer for tick-level KRX microstructure strategies.

Given a strategy idea (name, hypothesis, suggested_features), design concrete:
1. signal_rules: list of {feature, operator, threshold, score_contribution, description}
2. filters: list of {feature, operator, threshold, action, description}

Available features from the market state:
- order_imbalance: [-1, 1] order book imbalance
- depth_imbalance: [-1, 1] bid/ask depth imbalance
- spread_bps: spread in basis points
- trade_flow_imbalance: [-1, 1] recent trade direction imbalance
- bid_depth_5: total bid volume top 5 levels
- ask_depth_5: total ask volume top 5 levels
- volume_surprise: recent volume vs expected
- micro_price: microstructure-adjusted price

Operators: >, <, >=, <=, ==, cross_above, cross_below
Filter actions: block, reduce

Respond in JSON with keys "signal_rules" and "filters".
"""


class FactorDesignerAgent(BaseAgent):
    """Converts strategy ideas into concrete signal rules and filters."""

    def __init__(self, llm_client: Any | None = None, **kwargs) -> None:
        super().__init__(name="FactorDesigner", llm_client=llm_client, **kwargs)

    def run(self, input_data: dict) -> dict:
        """Design signal rules and filters for a strategy idea.

        Parameters
        ----------
        input_data : dict
            Keys: idea (dict from Researcher with name, hypothesis,
            suggested_features, expected_direction)

        Returns
        -------
        dict
            Keys: signal_rules (list[dict]), filters (list[dict])
        """
        idea = input_data.get("idea", {})
        idea_name = idea.get("name", "unknown")

        user_prompt = (
            f"Strategy idea: {idea.get('name', '')}\n"
            f"Hypothesis: {idea.get('hypothesis', '')}\n"
            f"Suggested features: {idea.get('suggested_features', [])}\n"
            f"Expected direction: {idea.get('expected_direction', '')}\n"
            f"Design signal rules and filters."
        )

        llm_response = self._query_llm(_SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(llm_response)

        if parsed and "signal_rules" in parsed:
            logger.info("[FactorDesigner] LLM designed %d rules for '%s'",
                        len(parsed["signal_rules"]), idea_name)
            return parsed

        # Fallback: heuristic design based on idea name
        logger.info("[FactorDesigner] Using heuristic design for '%s'", idea_name)
        return self._heuristic_design(idea)

    @staticmethod
    def _heuristic_design(idea: dict) -> dict:
        """Built-in rule designs for common strategy types."""
        name = idea.get("name", "")
        features = idea.get("suggested_features", [])

        if "imbalance" in name.lower():
            return {
                "signal_rules": [
                    {
                        "feature": "order_imbalance",
                        "operator": ">",
                        "threshold": 0.3,
                        "score_contribution": 0.5,
                        "description": "Strong bid-side imbalance => bullish signal",
                    },
                    {
                        "feature": "order_imbalance",
                        "operator": "<",
                        "threshold": -0.3,
                        "score_contribution": -0.5,
                        "description": "Strong ask-side imbalance => bearish signal",
                    },
                    {
                        "feature": "depth_imbalance",
                        "operator": ">",
                        "threshold": 0.2,
                        "score_contribution": 0.3,
                        "description": "Depth supports bullish imbalance",
                    },
                    {
                        "feature": "depth_imbalance",
                        "operator": "<",
                        "threshold": -0.2,
                        "score_contribution": -0.3,
                        "description": "Depth supports bearish imbalance",
                    },
                ],
                "filters": [
                    {
                        "feature": "spread_bps",
                        "operator": ">",
                        "threshold": 30.0,
                        "action": "block",
                        "description": "Skip when spread is too wide (illiquid)",
                    },
                ],
            }

        elif "spread" in name.lower():
            return {
                "signal_rules": [
                    {
                        "feature": "spread_bps",
                        "operator": ">",
                        "threshold": 10.0,
                        "score_contribution": 0.4,
                        "description": "Wide spread => mean reversion opportunity",
                    },
                    {
                        "feature": "order_imbalance",
                        "operator": "<",
                        "threshold": -0.2,
                        "score_contribution": 0.3,
                        "description": "Fade bearish imbalance during wide spread (contrarian)",
                    },
                    {
                        "feature": "order_imbalance",
                        "operator": ">",
                        "threshold": 0.2,
                        "score_contribution": -0.3,
                        "description": "Fade bullish imbalance during wide spread (contrarian)",
                    },
                ],
                "filters": [
                    {
                        "feature": "spread_bps",
                        "operator": "<",
                        "threshold": 3.0,
                        "action": "block",
                        "description": "No opportunity when spread is tight",
                    },
                ],
            }

        elif "trade_flow" in name.lower() or "pressure" in name.lower():
            return {
                "signal_rules": [
                    {
                        "feature": "trade_flow_imbalance",
                        "operator": ">",
                        "threshold": 0.4,
                        "score_contribution": 0.6,
                        "description": "Strong buy-side trade flow => follow momentum",
                    },
                    {
                        "feature": "trade_flow_imbalance",
                        "operator": "<",
                        "threshold": -0.4,
                        "score_contribution": -0.6,
                        "description": "Strong sell-side trade flow => follow momentum",
                    },
                ],
                "filters": [
                    {
                        "feature": "spread_bps",
                        "operator": ">",
                        "threshold": 25.0,
                        "action": "block",
                        "description": "Avoid chasing in illiquid conditions",
                    },
                ],
            }

        # Generic fallback
        primary_feature = features[0] if features else "order_imbalance"
        return {
            "signal_rules": [
                {
                    "feature": primary_feature,
                    "operator": ">",
                    "threshold": 0.3,
                    "score_contribution": 0.5,
                    "description": f"{primary_feature} > threshold => bullish",
                },
                {
                    "feature": primary_feature,
                    "operator": "<",
                    "threshold": -0.3,
                    "score_contribution": -0.5,
                    "description": f"{primary_feature} < threshold => bearish",
                },
            ],
            "filters": [],
        }
