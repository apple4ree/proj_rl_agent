"""Multi-Agent wrappers for strategy generation.

Each agent encapsulates:
- A system prompt with domain constraints
- A structured output schema
- An OpenAI client call
- A heuristic fallback when LLM is unavailable
"""
from __future__ import annotations

import logging
from typing import Any

from .agent_schemas import (
    ExitRuleDraft,
    FilterRuleDraft,
    IdeaBrief,
    IdeaBriefList,
    KNOWN_FEATURES_LIST,
    PositionRuleDraft,
    ReviewDecision,
    ReviewIssueDraft,
    RiskDraft,
    SignalDraft,
    SignalRuleDraft,
    VALID_EXIT_TYPES,
    VALID_OPERATORS,
    VALID_SIZING_MODES,
)
from .openai_client import OpenAIStrategyGenClient

logger = logging.getLogger(__name__)

# ── Shared prompt fragments ──────────────────────────────────────────

_FEATURES_BLOCK = f"""
ALLOWED FEATURES (use ONLY these):
{chr(10).join(f'  - {f}' for f in KNOWN_FEATURES_LIST)}
""".strip()

_OPERATORS_BLOCK = f"""
ALLOWED OPERATORS: {', '.join(VALID_OPERATORS)}
""".strip()

_SIZING_BLOCK = f"""
ALLOWED SIZING MODES: {', '.join(VALID_SIZING_MODES)}
""".strip()

_EXIT_TYPES_BLOCK = f"""
ALLOWED EXIT TYPES: {', '.join(VALID_EXIT_TYPES)}
""".strip()


# ── Researcher Agent ──────────────────────────────────────────────────

_RESEARCHER_SYSTEM = f"""You are a quantitative researcher specializing in KRX (Korea Exchange) tick-level microstructure strategies.

Given a research goal, propose strategy ideas that exploit LOB (Limit Order Book) microstructure patterns.

{_FEATURES_BLOCK}

Each idea must:
1. Have a clear, testable hypothesis
2. Reference only features from the allowed list above
3. Specify a style: momentum, mean_reversion, contrarian, microstructure, or statistical_arbitrage
4. Be realistically implementable with tick-level data

Keep names in snake_case (e.g., 'imbalance_momentum', 'spread_reversal').
"""


class ResearcherAgent:
    """Proposes strategy ideas from a research goal."""

    def __init__(self, client: OpenAIStrategyGenClient | None = None) -> None:
        self.client = client

    def run(self, research_goal: str, n_ideas: int = 3) -> IdeaBriefList:
        if self.client is not None:
            result = self.client.query_structured(
                system_prompt=_RESEARCHER_SYSTEM,
                user_prompt=f"Propose {n_ideas} tick-level strategy ideas for: {research_goal}",
                schema=IdeaBriefList,
            )
            if result is not None:
                return result
            logger.info("ResearcherAgent: LLM unavailable, using fallback")
        return self._fallback(research_goal, n_ideas)

    def _fallback(self, research_goal: str, n_ideas: int) -> IdeaBriefList:
        """Deterministic fallback: produce ideas from template keywords."""
        ideas = [
            IdeaBrief(
                name="imbalance_momentum",
                thesis="Order book imbalance predicts short-term price direction",
                core_features=["order_imbalance", "depth_imbalance", "trade_flow_imbalance"],
                style="momentum",
                rationale="Heavy bid side → price likely to rise in next ticks",
            ),
            IdeaBrief(
                name="spread_mean_reversion",
                thesis="Spread widens temporarily then reverts, providing contrarian entry",
                core_features=["spread_bps", "order_imbalance", "mid_price"],
                style="mean_reversion",
                rationale="Wide spread = temporary liquidity shock → fade the move",
            ),
            IdeaBrief(
                name="trade_flow_pressure",
                thesis="Sustained directional trade flow predicts continuation",
                core_features=["trade_flow_imbalance", "volume_surprise", "recent_volume"],
                style="momentum",
                rationale="Aggressive trade flow indicates informed trading",
            ),
        ]
        return IdeaBriefList(ideas=ideas[:n_ideas])


# ── Factor Designer Agent ─────────────────────────────────────────────

_FACTOR_SYSTEM = f"""You are a quantitative factor designer for KRX tick-level strategies.

Given a strategy idea, design signal rules and pre-trade filters.

{_FEATURES_BLOCK}

{_OPERATORS_BLOCK}

RULES:
1. Use ONLY features from the allowed list
2. Use ONLY operators from the allowed list
3. Each signal rule needs: feature, operator, threshold, score_contribution, description
4. score_contribution: positive = bullish signal, negative = bearish signal
5. Filters use action "block" (skip signal) or "reduce" (halve score)
6. Keep rules to 3-6 signal rules and 0-3 filters
7. Ensure both positive and negative score contributions for balanced coverage
"""


class FactorDesignerAgent:
    """Designs signal rules and filters for a strategy idea."""

    def __init__(self, client: OpenAIStrategyGenClient | None = None) -> None:
        self.client = client

    def run(self, idea: IdeaBrief) -> SignalDraft:
        if self.client is not None:
            result = self.client.query_structured(
                system_prompt=_FACTOR_SYSTEM,
                user_prompt=(
                    f"Design signal rules for strategy '{idea.name}'.\n"
                    f"Thesis: {idea.thesis}\n"
                    f"Core features: {', '.join(idea.core_features)}\n"
                    f"Style: {idea.style}"
                ),
                schema=SignalDraft,
            )
            if result is not None:
                return result
            logger.info("FactorDesignerAgent: LLM unavailable, using fallback")
        return self._fallback(idea)

    def _fallback(self, idea: IdeaBrief) -> SignalDraft:
        """Heuristic fallback based on idea style and features."""
        features = idea.core_features or ["order_imbalance"]
        primary = features[0]

        if idea.style in ("momentum", "microstructure"):
            rules = [
                SignalRuleDraft(feature=primary, operator=">", threshold=0.3,
                                score_contribution=0.5, description=f"Bullish {primary}"),
                SignalRuleDraft(feature=primary, operator="<", threshold=-0.3,
                                score_contribution=-0.5, description=f"Bearish {primary}"),
            ]
        else:  # mean_reversion, contrarian
            rules = [
                SignalRuleDraft(feature=primary, operator=">", threshold=0.5,
                                score_contribution=-0.4, description=f"Contrarian sell on high {primary}"),
                SignalRuleDraft(feature=primary, operator="<", threshold=-0.5,
                                score_contribution=0.4, description=f"Contrarian buy on low {primary}"),
            ]

        # Add depth feature if available
        if len(features) > 1 and features[1] in ("depth_imbalance", "trade_flow_imbalance"):
            sec = features[1]
            rules.append(SignalRuleDraft(
                feature=sec, operator=">", threshold=0.2,
                score_contribution=0.3, description=f"Supporting bullish {sec}",
            ))
            rules.append(SignalRuleDraft(
                feature=sec, operator="<", threshold=-0.2,
                score_contribution=-0.3, description=f"Supporting bearish {sec}",
            ))

        filters = [
            FilterRuleDraft(feature="spread_bps", operator=">", threshold=30.0,
                            action="block", description="Block on wide spread"),
        ]

        return SignalDraft(signal_rules=rules, filters=filters, rationale="Heuristic fallback")


# ── Risk Designer Agent ────────────────────────────────────────────────

_RISK_SYSTEM = f"""You are a risk and execution designer for KRX tick-level strategies.

Given a strategy idea and its signal rules, design position sizing and exit rules.

{_SIZING_BLOCK}

{_EXIT_TYPES_BLOCK}

RULES:
1. Always include stop_loss and time_exit
2. stop_loss threshold_bps: 10-30 for tick strategies
3. take_profit threshold_bps: 15-50 for tick strategies
4. time_exit timeout_ticks: 100-1000 for tick strategies
5. max_position: 100-1000 shares for KRX large-caps
6. inventory_cap >= max_position
7. holding_period_ticks: 5-100 (will be scaled by latency)
"""


class RiskDesignerAgent:
    """Designs position rules and exit rules."""

    def __init__(self, client: OpenAIStrategyGenClient | None = None) -> None:
        self.client = client

    def run(self, idea: IdeaBrief, signal_draft: SignalDraft, latency_ms: float = 1.0) -> RiskDraft:
        if self.client is not None:
            result = self.client.query_structured(
                system_prompt=_RISK_SYSTEM,
                user_prompt=(
                    f"Design risk/exit rules for strategy '{idea.name}'.\n"
                    f"Style: {idea.style}\n"
                    f"Signal rules: {len(signal_draft.signal_rules)}\n"
                    f"Expected latency: {latency_ms}ms\n"
                    f"Thesis: {idea.thesis}"
                ),
                schema=RiskDraft,
            )
            if result is not None:
                return result
            logger.info("RiskDesignerAgent: LLM unavailable, using fallback")
        return self._fallback(idea, latency_ms)

    def _fallback(self, idea: IdeaBrief, latency_ms: float) -> RiskDraft:
        """Conservative heuristic risk parameters."""
        return RiskDraft(
            position_rule=PositionRuleDraft(
                max_position=500,
                sizing_mode="signal_proportional",
                fixed_size=100,
                holding_period_ticks=10,
                inventory_cap=1000,
            ),
            exit_rules=[
                ExitRuleDraft(exit_type="stop_loss", threshold_bps=15.0,
                              description="Stop loss at 15 bps"),
                ExitRuleDraft(exit_type="take_profit", threshold_bps=25.0,
                              description="Take profit at 25 bps"),
                ExitRuleDraft(exit_type="time_exit", timeout_ticks=300,
                              description="Time exit after 300 ticks"),
            ],
            latency_notes=f"Designed for {latency_ms}ms latency",
        )


# ── LLM Reviewer Agent ────────────────────────────────────────────────

_REVIEWER_SYSTEM = f"""You are a quantitative strategy reviewer for KRX tick-level strategies.

Review the strategy specification for issues:
1. Signal rules: balanced (buy + sell), reasonable thresholds, known features
2. Filters: not too restrictive, realistic thresholds
3. Risk: stop_loss present, time_exit present, reasonable bps levels
4. Position: reasonable sizing, inventory_cap >= max_position
5. Redundancy: no duplicate rules

{_FEATURES_BLOCK}

Set approved=true only if there are no errors (warnings/info are ok).
"""


class LLMReviewerAgent:
    """LLM-based soft review (complement to the static StrategyReviewer)."""

    def __init__(self, client: OpenAIStrategyGenClient | None = None) -> None:
        self.client = client

    def run(self, spec_dict: dict[str, Any]) -> ReviewDecision:
        if self.client is not None:
            import json
            result = self.client.query_structured(
                system_prompt=_REVIEWER_SYSTEM,
                user_prompt=f"Review this strategy spec:\n{json.dumps(spec_dict, indent=2)}",
                schema=ReviewDecision,
            )
            if result is not None:
                return result
            logger.info("LLMReviewerAgent: LLM unavailable, using fallback")
        return self._fallback(spec_dict)

    def _fallback(self, spec_dict: dict[str, Any]) -> ReviewDecision:
        """Fallback: delegate to the static StrategyReviewer."""
        from strategy_specs.schema import StrategySpec
        from strategy_review.reviewer import StrategyReviewer

        spec = StrategySpec.from_dict(spec_dict)
        reviewer = StrategyReviewer()
        result = reviewer.review(spec)

        issues = [
            ReviewIssueDraft(
                category=issue.category,
                severity=issue.severity,
                description=issue.description,
                suggestion=issue.suggestion,
            )
            for issue in result.issues
        ]

        return ReviewDecision(
            approved=result.passed,
            issues=issues,
            confidence=1.0 if result.passed else 0.3,
        )
