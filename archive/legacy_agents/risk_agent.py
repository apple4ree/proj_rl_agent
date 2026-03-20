"""
llm_agents/risk_agent.py
------------------------
Risk / Execution Agent: adds position sizing rules, exit conditions,
holding constraints, inventory caps, and latency-aware adjustments.

Input:  signal_rules, filters from Factor Designer + idea context
Output: position_rule, exit_rules, updated filters
"""
from __future__ import annotations

import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a risk management and execution specialist for tick-level KRX strategies.

Given signal rules and filters for a strategy, design:
1. position_rule: {max_position, sizing_mode, fixed_size, holding_period_ticks, inventory_cap}
2. exit_rules: list of {exit_type, threshold_bps, timeout_ticks, description}
3. additional_filters: any extra risk filters to add

Available exit types: stop_loss, take_profit, trailing_stop, time_exit, signal_reversal
Sizing modes: fixed, signal_proportional, kelly

Consider:
- KRX tick-level execution realities (spread cost, impact)
- Latency effects on execution
- Position concentration risk
- Typical holding periods for microstructure strategies (seconds to minutes)

Respond in JSON with keys "position_rule", "exit_rules", "additional_filters".
"""


class RiskExecutionAgent(BaseAgent):
    """Adds risk management, position sizing, and exit rules to a strategy."""

    def __init__(self, llm_client: Any | None = None, **kwargs) -> None:
        super().__init__(name="RiskExecution", llm_client=llm_client, **kwargs)

    def run(self, input_data: dict) -> dict:
        """Design risk and execution rules.

        Parameters
        ----------
        input_data : dict
            Keys: idea (dict), signal_rules (list), filters (list),
            latency_ms (float, optional)

        Returns
        -------
        dict
            Keys: position_rule (dict), exit_rules (list[dict]),
            additional_filters (list[dict])
        """
        idea = input_data.get("idea", {})
        signal_rules = input_data.get("signal_rules", [])
        filters = input_data.get("filters", [])
        latency_ms = input_data.get("latency_ms", 1.0)

        user_prompt = (
            f"Strategy: {idea.get('name', 'unknown')}\n"
            f"Hypothesis: {idea.get('hypothesis', '')}\n"
            f"Signal rules: {signal_rules}\n"
            f"Current filters: {filters}\n"
            f"Expected latency: {latency_ms}ms\n"
            f"Design position rules, exit rules, and additional risk filters."
        )

        llm_response = self._query_llm(_SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(llm_response)

        if parsed and "position_rule" in parsed:
            logger.info("[RiskExecution] LLM designed risk rules for '%s'",
                        idea.get("name", "unknown"))
            return parsed

        logger.info("[RiskExecution] Using heuristic risk rules")
        return self._heuristic_risk(idea, latency_ms)

    @staticmethod
    def _heuristic_risk(idea: dict, latency_ms: float = 1.0) -> dict:
        """Built-in risk rules calibrated for tick-level microstructure."""
        name = idea.get("name", "")

        # Adjust holding period based on latency
        # Higher latency => longer minimum hold to avoid whipsaw
        base_hold = 5
        if latency_ms > 100:
            base_hold = 30
        elif latency_ms > 50:
            base_hold = 20
        elif latency_ms > 10:
            base_hold = 10

        # Strategy-specific adjustments
        if "momentum" in name.lower() or "pressure" in name.lower():
            position_rule = {
                "max_position": 500,
                "sizing_mode": "signal_proportional",
                "fixed_size": 100,
                "holding_period_ticks": base_hold,
                "inventory_cap": 500,
            }
            exit_rules = [
                {
                    "exit_type": "stop_loss",
                    "threshold_bps": 15.0,
                    "timeout_ticks": 0,
                    "description": "Cut losses at 15 bps",
                },
                {
                    "exit_type": "take_profit",
                    "threshold_bps": 25.0,
                    "timeout_ticks": 0,
                    "description": "Take profit at 25 bps",
                },
                {
                    "exit_type": "time_exit",
                    "threshold_bps": 0.0,
                    "timeout_ticks": 300,
                    "description": "Force exit after 300 ticks (5 min at 1s)",
                },
            ]
        elif "reversion" in name.lower() or "spread" in name.lower():
            position_rule = {
                "max_position": 300,
                "sizing_mode": "fixed",
                "fixed_size": 100,
                "holding_period_ticks": base_hold * 2,
                "inventory_cap": 300,
            }
            exit_rules = [
                {
                    "exit_type": "stop_loss",
                    "threshold_bps": 20.0,
                    "timeout_ticks": 0,
                    "description": "Wider stop for mean reversion (20 bps)",
                },
                {
                    "exit_type": "take_profit",
                    "threshold_bps": 10.0,
                    "timeout_ticks": 0,
                    "description": "Tighter target for mean reversion (10 bps)",
                },
                {
                    "exit_type": "trailing_stop",
                    "threshold_bps": 8.0,
                    "timeout_ticks": 0,
                    "description": "Trailing stop at 8 bps from peak",
                },
                {
                    "exit_type": "time_exit",
                    "threshold_bps": 0.0,
                    "timeout_ticks": 600,
                    "description": "Force exit after 600 ticks",
                },
            ]
        else:
            position_rule = {
                "max_position": 500,
                "sizing_mode": "signal_proportional",
                "fixed_size": 100,
                "holding_period_ticks": base_hold,
                "inventory_cap": 500,
            }
            exit_rules = [
                {
                    "exit_type": "stop_loss",
                    "threshold_bps": 15.0,
                    "timeout_ticks": 0,
                    "description": "Default stop loss at 15 bps",
                },
                {
                    "exit_type": "take_profit",
                    "threshold_bps": 20.0,
                    "timeout_ticks": 0,
                    "description": "Default take profit at 20 bps",
                },
                {
                    "exit_type": "time_exit",
                    "threshold_bps": 0.0,
                    "timeout_ticks": 300,
                    "description": "Default time exit at 300 ticks",
                },
            ]

        additional_filters = []
        if latency_ms > 50:
            additional_filters.append({
                "feature": "spread_bps",
                "operator": "<",
                "threshold": 5.0,
                "action": "block",
                "description": f"High latency ({latency_ms}ms): only trade wide spreads",
            })

        return {
            "position_rule": position_rule,
            "exit_rules": exit_rules,
            "additional_filters": additional_filters,
        }
