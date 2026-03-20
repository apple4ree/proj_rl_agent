"""
llm_agents/researcher.py
------------------------
Researcher Agent: generates strategy ideas from market context and research goals.

Input:  research_goal (str), market_context (dict), constraints (dict)
Output: list of strategy ideas with name, hypothesis, rationale, suggested features
"""
from __future__ import annotations

import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a quantitative researcher specializing in tick-level microstructure strategies
for the Korean stock exchange (KRX).

Given a research goal and market context, generate strategy ideas.
Each idea should include:
- name: short strategy name
- hypothesis: what market inefficiency this exploits
- rationale: why this should work at tick-level
- suggested_features: list of feature names to use
- expected_direction: how the signal maps to buy/sell
- risk_notes: known risks or failure modes

Respond in JSON with key "ideas" containing a list of idea objects.
"""


class ResearcherAgent(BaseAgent):
    """Generates strategy ideas from research goals and market context."""

    def __init__(self, llm_client: Any | None = None, **kwargs) -> None:
        super().__init__(name="Researcher", llm_client=llm_client, **kwargs)

    def run(self, input_data: dict) -> dict:
        """Generate strategy ideas.

        Parameters
        ----------
        input_data : dict
            Keys: research_goal (str), market_context (dict), n_ideas (int)

        Returns
        -------
        dict
            Keys: ideas (list[dict]) with name, hypothesis, rationale,
            suggested_features, expected_direction, risk_notes
        """
        research_goal = input_data.get("research_goal", "Generate a tick-level alpha strategy")
        market_context = input_data.get("market_context", {})
        n_ideas = input_data.get("n_ideas", 3)

        user_prompt = (
            f"Research goal: {research_goal}\n"
            f"Market context: {market_context}\n"
            f"Generate {n_ideas} strategy ideas."
        )

        llm_response = self._query_llm(_SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(llm_response)

        if parsed and "ideas" in parsed:
            logger.info("[Researcher] LLM generated %d ideas", len(parsed["ideas"]))
            return parsed

        # Fallback: built-in heuristic ideas
        logger.info("[Researcher] Using built-in heuristic ideas (no LLM)")
        return {"ideas": self._default_ideas(n_ideas)}

    @staticmethod
    def _default_ideas(n: int = 3) -> list[dict]:
        """Built-in strategy ideas for mock/offline mode."""
        ideas = [
            {
                "name": "imbalance_momentum",
                "hypothesis": "Order book imbalance predicts short-term price direction",
                "rationale": "When bid depth significantly exceeds ask depth, buying pressure "
                             "tends to push price up within the next few ticks",
                "suggested_features": ["order_imbalance", "depth_imbalance", "trade_flow_imbalance"],
                "expected_direction": "imbalance > 0 => BUY, imbalance < 0 => SELL",
                "risk_notes": "Fails during large institutional block orders that create "
                              "misleading imbalance",
            },
            {
                "name": "spread_mean_reversion",
                "hypothesis": "Spread widening indicates temporary liquidity withdrawal; "
                              "price reverts when liquidity returns",
                "rationale": "Spread spikes are transient; providing liquidity during wide "
                             "spreads captures the reversion",
                "suggested_features": ["spread_bps", "order_imbalance", "bid_depth_5", "ask_depth_5"],
                "expected_direction": "Wide spread + imbalance => fade the imbalance direction",
                "risk_notes": "Spread widening can be permanent during news events",
            },
            {
                "name": "trade_flow_pressure",
                "hypothesis": "Sustained one-directional trade flow indicates informed trading",
                "rationale": "When trade flow imbalance persists for multiple ticks, it signals "
                             "informed order flow that will move the price",
                "suggested_features": ["trade_flow_imbalance", "recent_volume", "order_imbalance"],
                "expected_direction": "trade_flow > threshold => follow the flow direction",
                "risk_notes": "May chase momentum too late; needs exit discipline",
            },
        ]
        return ideas[:n]
