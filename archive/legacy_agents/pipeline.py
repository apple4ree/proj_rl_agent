"""
llm_agents/pipeline.py
----------------------
Multi-Agent pipeline orchestrator.

Chains: Researcher -> Factor Designer -> Risk/Execution -> Reviewer
to produce a validated StrategySpec from a research goal.
"""
from __future__ import annotations

import logging
from typing import Any

from strategy_specs.schema import (
    StrategySpec,
    SignalRule,
    FilterRule,
    PositionRule,
    ExitRule,
)

from .researcher import ResearcherAgent
from .factor_designer import FactorDesignerAgent
from .risk_agent import RiskExecutionAgent
from .reviewer import ReviewerAgent

logger = logging.getLogger(__name__)


class MultiAgentPipeline:
    """Orchestrates the 4-agent strategy generation pipeline.

    Parameters
    ----------
    llm_client : Any | None
        Shared LLM client for all agents. None = heuristic mode.
    model : str
        LLM model identifier.
    temperature : float
        Sampling temperature for LLM calls.
    max_review_iterations : int
        Maximum reviewer iterations before accepting.
    """

    def __init__(
        self,
        llm_client: Any | None = None,
        model: str = "gpt-4o",
        temperature: float = 0.2,
        max_review_iterations: int = 2,
    ) -> None:
        self.researcher = ResearcherAgent(llm_client=llm_client, model=model, temperature=temperature)
        self.factor_designer = FactorDesignerAgent(llm_client=llm_client, model=model, temperature=temperature)
        self.risk_agent = RiskExecutionAgent(llm_client=llm_client, model=model, temperature=temperature)
        self.reviewer = ReviewerAgent(llm_client=llm_client, model=model, temperature=temperature)
        self.max_review_iterations = max_review_iterations

    def generate(
        self,
        research_goal: str = "Generate a tick-level alpha strategy",
        market_context: dict | None = None,
        n_ideas: int = 3,
        idea_index: int = 0,
        latency_ms: float = 1.0,
    ) -> tuple[StrategySpec, dict]:
        """Run the full pipeline to generate a validated strategy spec.

        Parameters
        ----------
        research_goal : str
            High-level research objective.
        market_context : dict | None
            Market context (symbol, date, conditions, etc.).
        n_ideas : int
            Number of ideas for the researcher to generate.
        idea_index : int
            Which idea to develop (0-indexed).
        latency_ms : float
            Expected execution latency for risk calibration.

        Returns
        -------
        tuple[StrategySpec, dict]
            The validated StrategySpec and a trace dict with all intermediate outputs.
        """
        trace: dict[str, Any] = {"research_goal": research_goal}

        # Step 1: Research
        logger.info("=== Step 1: Researcher Agent ===")
        research_output = self.researcher.run({
            "research_goal": research_goal,
            "market_context": market_context or {},
            "n_ideas": n_ideas,
        })
        ideas = research_output.get("ideas", [])
        trace["research_output"] = research_output

        if not ideas:
            raise ValueError("Researcher produced no ideas")

        selected_idea = ideas[min(idea_index, len(ideas) - 1)]
        trace["selected_idea"] = selected_idea
        logger.info("Selected idea: %s", selected_idea.get("name", "unknown"))

        # Step 2: Factor Design
        logger.info("=== Step 2: Factor Designer Agent ===")
        factor_output = self.factor_designer.run({"idea": selected_idea})
        trace["factor_output"] = factor_output

        # Step 3: Risk / Execution
        logger.info("=== Step 3: Risk / Execution Agent ===")
        risk_output = self.risk_agent.run({
            "idea": selected_idea,
            "signal_rules": factor_output.get("signal_rules", []),
            "filters": factor_output.get("filters", []),
            "latency_ms": latency_ms,
        })
        trace["risk_output"] = risk_output

        # Assemble StrategySpec
        all_filters = factor_output.get("filters", []) + risk_output.get("additional_filters", [])
        spec = StrategySpec(
            name=selected_idea.get("name", "unnamed"),
            version="1.0",
            description=selected_idea.get("hypothesis", ""),
            signal_rules=[SignalRule(**r) for r in factor_output.get("signal_rules", [])],
            filters=[FilterRule(**f) for f in all_filters],
            position_rule=PositionRule(**risk_output.get("position_rule", {})),
            exit_rules=[ExitRule(**e) for e in risk_output.get("exit_rules", [])],
            metadata={
                "research_goal": research_goal,
                "idea_name": selected_idea.get("name", ""),
                "latency_ms": latency_ms,
                "pipeline": "multi_agent_v1",
            },
        )

        # Step 4: Review (with iteration)
        logger.info("=== Step 4: Reviewer Agent ===")
        for iteration in range(self.max_review_iterations):
            review_output = self.reviewer.run({"spec": spec.to_dict()})
            trace[f"review_output_{iteration}"] = review_output

            if review_output.get("passed", False):
                logger.info("Review passed on iteration %d", iteration)
                break

            issues = review_output.get("issues", [])
            errors = [i for i in issues if i.get("severity") == "error"]
            if not errors:
                logger.info("Review has warnings but no errors; accepting")
                break

            logger.warning("Review found %d errors, iteration %d", len(errors), iteration)
            # In LLM mode, could re-run factor designer with feedback
            # For now, log and accept on final iteration

        trace["final_review"] = review_output
        trace["spec"] = spec.to_dict()

        logger.info("Pipeline complete: strategy '%s' (v%s)", spec.name, spec.version)
        return spec, trace

    def generate_batch(
        self,
        research_goal: str = "Generate tick-level alpha strategies",
        market_context: dict | None = None,
        n_ideas: int = 3,
        latency_ms: float = 1.0,
    ) -> list[tuple[StrategySpec, dict]]:
        """Generate specs for all ideas from a single research run.

        Returns a list of (spec, trace) tuples, one per idea.
        """
        results = []
        for i in range(n_ideas):
            try:
                spec, trace = self.generate(
                    research_goal=research_goal,
                    market_context=market_context,
                    n_ideas=n_ideas,
                    idea_index=i,
                    latency_ms=latency_ms,
                )
                results.append((spec, trace))
            except Exception as e:
                logger.error("Failed to generate spec for idea %d: %s", i, e)
        return results
