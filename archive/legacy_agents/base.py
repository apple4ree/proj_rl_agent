"""
llm_agents/base.py
------------------
Base class for all LLM agents in the Multi-Agent pipeline.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for LLM-powered strategy agents.

    Each agent takes structured input, optionally queries an LLM,
    and produces structured output consumable by the next agent.

    Parameters
    ----------
    name : str
        Agent role name.
    llm_client : Any | None
        LLM client (e.g. OpenAI). None = use built-in heuristics (mock mode).
    model : str
        LLM model identifier.
    temperature : float
        Sampling temperature.
    """

    def __init__(
        self,
        name: str,
        llm_client: Any | None = None,
        model: str = "gpt-4o",
        temperature: float = 0.2,
    ) -> None:
        self.name = name
        self.llm_client = llm_client
        self.model = model
        self.temperature = temperature

    @abstractmethod
    def run(self, input_data: dict) -> dict:
        """Execute this agent's task.

        Parameters
        ----------
        input_data : dict
            Structured input from the previous agent or the user.

        Returns
        -------
        dict
            Structured output for the next agent.
        """

    def _query_llm(self, system_prompt: str, user_prompt: str) -> str | None:
        """Query the LLM and return the response text."""
        if self.llm_client is None:
            return None

        try:
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning("[%s] LLM query failed: %s", self.name, e)
            return None

    def _parse_json_response(self, text: str | None) -> dict | None:
        """Parse JSON from LLM response text."""
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("[%s] Failed to parse LLM JSON: %s", self.name, e)
            return None
