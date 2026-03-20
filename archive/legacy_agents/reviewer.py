"""
llm_agents/reviewer.py
----------------------
Reviewer Agent: validates a complete StrategySpec for:
- Look-ahead bias risks
- Excessive complexity
- Non-executable rules
- Redundant rules
- Unrealistic parameters

Input:  complete StrategySpec (as dict)
Output: review results with pass/fail, issues, and optional modifications
"""
from __future__ import annotations

import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior quantitative strategy reviewer for tick-level KRX microstructure.

Review the strategy specification for:
1. look_ahead_bias: any rule that requires future information
2. excessive_complexity: too many rules that may overfit
3. non_executable_rules: rules referencing unavailable features
4. redundant_rules: duplicate or contradictory rules
5. unrealistic_parameters: thresholds that are too tight or too loose
6. missing_risk_controls: no stop loss, no position limits, etc.

For each issue found, provide:
- category: one of the above
- severity: "error" (must fix), "warning" (should fix), "info" (suggestion)
- description: what the issue is
- suggestion: how to fix it

Respond in JSON with keys:
- "passed": bool (true if no errors)
- "issues": list of issue objects
- "modifications": optional dict of suggested changes to the spec
"""

# Features available from MarketState + FeaturePipeline
_AVAILABLE_FEATURES = {
    "mid_price", "spread_bps", "order_imbalance", "best_bid", "best_ask",
    "bid_depth_5", "ask_depth_5", "depth_imbalance",
    "price_impact_buy", "price_impact_sell", "trade_flow_imbalance",
    "volume_surprise", "micro_price", "trade_count", "recent_volume",
    "bid_depth", "ask_depth",
}


class ReviewerAgent(BaseAgent):
    """Reviews a complete strategy spec for issues and quality."""

    def __init__(self, llm_client: Any | None = None, **kwargs) -> None:
        super().__init__(name="Reviewer", llm_client=llm_client, **kwargs)

    def run(self, input_data: dict) -> dict:
        """Review a strategy specification.

        Parameters
        ----------
        input_data : dict
            Keys: spec (dict representation of StrategySpec)

        Returns
        -------
        dict
            Keys: passed (bool), issues (list[dict]), modifications (dict | None)
        """
        spec = input_data.get("spec", {})

        user_prompt = f"Review this strategy specification:\n{spec}"
        llm_response = self._query_llm(_SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(llm_response)

        if parsed and "passed" in parsed:
            logger.info("[Reviewer] LLM review: passed=%s, %d issues",
                        parsed["passed"], len(parsed.get("issues", [])))
            return parsed

        logger.info("[Reviewer] Using heuristic review")
        return self._heuristic_review(spec)

    @staticmethod
    def _heuristic_review(spec: dict) -> dict:
        """Built-in validation checks."""
        issues: list[dict] = []

        signal_rules = spec.get("signal_rules", [])
        filters = spec.get("filters", [])
        position_rule = spec.get("position_rule", {})
        exit_rules = spec.get("exit_rules", [])

        # Check: no signal rules
        if not signal_rules:
            issues.append({
                "category": "non_executable_rules",
                "severity": "error",
                "description": "No signal rules defined",
                "suggestion": "Add at least one signal rule",
            })

        # Check: unavailable features
        for i, rule in enumerate(signal_rules):
            feature = rule.get("feature", "")
            if feature and feature not in _AVAILABLE_FEATURES:
                issues.append({
                    "category": "non_executable_rules",
                    "severity": "warning",
                    "description": f"signal_rules[{i}]: feature '{feature}' may not be available",
                    "suggestion": f"Use one of: {sorted(_AVAILABLE_FEATURES)}",
                })

        for i, f in enumerate(filters):
            feature = f.get("feature", "")
            if feature and feature not in _AVAILABLE_FEATURES:
                issues.append({
                    "category": "non_executable_rules",
                    "severity": "warning",
                    "description": f"filters[{i}]: feature '{feature}' may not be available",
                    "suggestion": f"Use one of: {sorted(_AVAILABLE_FEATURES)}",
                })

        # Check: excessive complexity
        if len(signal_rules) > 10:
            issues.append({
                "category": "excessive_complexity",
                "severity": "warning",
                "description": f"{len(signal_rules)} signal rules may overfit",
                "suggestion": "Consider reducing to 3-6 core rules",
            })

        # Check: redundant rules (same feature + operator + threshold)
        seen_rules = set()
        for i, rule in enumerate(signal_rules):
            key = (rule.get("feature"), rule.get("operator"), rule.get("threshold"))
            if key in seen_rules:
                issues.append({
                    "category": "redundant_rules",
                    "severity": "warning",
                    "description": f"signal_rules[{i}] is a duplicate",
                    "suggestion": "Remove duplicate rule",
                })
            seen_rules.add(key)

        # Check: missing risk controls
        has_stop = any(e.get("exit_type") == "stop_loss" for e in exit_rules)
        has_time = any(e.get("exit_type") == "time_exit" for e in exit_rules)
        if not has_stop:
            issues.append({
                "category": "missing_risk_controls",
                "severity": "warning",
                "description": "No stop_loss exit rule",
                "suggestion": "Add a stop_loss with threshold_bps between 10-30",
            })
        if not has_time:
            issues.append({
                "category": "missing_risk_controls",
                "severity": "info",
                "description": "No time_exit rule; positions could be held indefinitely",
                "suggestion": "Consider adding a time_exit as a safety net",
            })

        # Check: unrealistic parameters
        max_pos = position_rule.get("max_position", 0)
        if max_pos > 5000:
            issues.append({
                "category": "unrealistic_parameters",
                "severity": "warning",
                "description": f"max_position={max_pos} is very large for tick-level strategy",
                "suggestion": "Consider max_position <= 2000",
            })

        for e in exit_rules:
            if e.get("exit_type") == "stop_loss" and e.get("threshold_bps", 0) > 100:
                issues.append({
                    "category": "unrealistic_parameters",
                    "severity": "warning",
                    "description": f"Stop loss at {e['threshold_bps']} bps is very wide",
                    "suggestion": "Typical tick-level stop loss: 10-50 bps",
                })

        # Check: contradictory score contributions
        total_positive = sum(r.get("score_contribution", 0)
                             for r in signal_rules if r.get("score_contribution", 0) > 0)
        total_negative = sum(r.get("score_contribution", 0)
                             for r in signal_rules if r.get("score_contribution", 0) < 0)
        if total_positive == 0 and total_negative == 0:
            issues.append({
                "category": "non_executable_rules",
                "severity": "error",
                "description": "All score contributions are zero; strategy will never generate signals",
                "suggestion": "Add non-zero score_contribution values",
            })

        has_errors = any(i["severity"] == "error" for i in issues)
        return {
            "passed": not has_errors,
            "issues": issues,
            "modifications": None,
        }
