"""
strategy_registry/registry.py
-----------------------------
Registry for managing strategy specs and their compiled versions.
Handles saving, loading, listing, and versioning of strategy specs.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator

from strategy_specs.schema import StrategySpec
from strategy_compiler.compiler import StrategyCompiler, CompiledStrategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """File-based registry for strategy specifications.

    Parameters
    ----------
    registry_dir : str | Path
        Directory to store strategy spec JSON files.
    """

    def __init__(self, registry_dir: str | Path = "strategies/") -> None:
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)

    def save(self, spec: StrategySpec) -> Path:
        """Save a strategy spec to the registry.

        Returns the path where the spec was saved.
        """
        filename = f"{spec.name}_v{spec.version}.json"
        path = self.registry_dir / filename
        spec.save(path)
        logger.info("Saved strategy '%s' to %s", spec.name, path)
        return path

    def load(self, name: str, version: str | None = None) -> StrategySpec:
        """Load a strategy spec by name and optional version.

        If version is None, loads the latest version.
        """
        if version:
            path = self.registry_dir / f"{name}_v{version}.json"
            if not path.exists():
                raise FileNotFoundError(f"Strategy not found: {path}")
            return StrategySpec.load(path)

        # Find latest version
        candidates = sorted(self.registry_dir.glob(f"{name}_v*.json"))
        if not candidates:
            raise FileNotFoundError(f"No strategy named '{name}' in registry")
        return StrategySpec.load(candidates[-1])

    def compile(self, name: str, version: str | None = None) -> CompiledStrategy:
        """Load and compile a strategy spec."""
        spec = self.load(name, version)
        return StrategyCompiler.compile(spec)

    def list_strategies(self) -> list[dict]:
        """List all strategies in the registry."""
        result = []
        for path in sorted(self.registry_dir.glob("*.json")):
            try:
                spec = StrategySpec.load(path)
                result.append({
                    "name": spec.name,
                    "version": spec.version,
                    "description": spec.description,
                    "n_signal_rules": len(spec.signal_rules),
                    "n_filters": len(spec.filters),
                    "n_exit_rules": len(spec.exit_rules),
                    "path": str(path),
                })
            except Exception as e:
                logger.warning("Failed to load %s: %s", path, e)
        return result

    def iter_specs(self) -> Iterator[StrategySpec]:
        """Iterate over all strategy specs in the registry."""
        for path in sorted(self.registry_dir.glob("*.json")):
            try:
                yield StrategySpec.load(path)
            except Exception as e:
                logger.warning("Failed to load %s: %s", path, e)
