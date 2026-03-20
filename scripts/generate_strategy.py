"""
전략 사양 생성 스크립트.

사용법:
    cd /home/dgu/tick/proj_rl_agent

    # Template backend (기본)
    PYTHONPATH=src python scripts/generate_strategy.py --goal "Order imbalance alpha"

    # OpenAI multi-agent backend
    OPENAI_API_KEY=sk-... PYTHONPATH=src python scripts/generate_strategy.py \
        --goal "Order imbalance alpha" --backend openai
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from strategy_generation import StrategyGenerator
from strategy_registry import StrategyRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate strategy specs")
    parser.add_argument("--goal", default="Generate tick-level alpha strategies for KRX",
                        help="Research goal — used to select matching templates or prompt LLM")
    parser.add_argument("--backend", choices=["template", "openai"], default="template",
                        help="Generation backend (default: template)")
    parser.add_argument("--mode", choices=["live", "mock", "replay"], default="live",
                        help="OpenAI client mode (default: live). Only used with --backend openai")
    parser.add_argument("--replay-path", default=None,
                        help="Replay log path for OpenAI mode")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Internal defaults
    output_dir = "strategies/"
    trace_dir_path = Path("outputs/strategy_traces/")

    generator = StrategyGenerator(
        latency_ms=1.0,
        backend=args.backend,
        mode=args.mode,
        replay_path=args.replay_path,
    )
    registry = StrategyRegistry(output_dir)
    trace_dir_path.mkdir(parents=True, exist_ok=True)

    spec, trace = generator.generate(
        research_goal=args.goal,
        n_ideas=3,
        idea_index=0,
    )
    results = [(spec, trace)]

    print(f"\n{'=' * 60}")
    print(f"Generated {len(results)} strategy spec(s)")
    if args.backend == "openai":
        mode_label = "OpenAI multi-agent" if not trace.get("fallback_used") else "OpenAI → template fallback"
        print(f"Backend: {mode_label}")
    else:
        print(f"Backend: template")
    print(f"{'=' * 60}")

    for i, (spec, trace) in enumerate(results):
        spec_path = registry.save(spec)

        trace_path = trace_dir_path / f"{spec.name}_trace.json"
        trace_path.write_text(
            json.dumps(trace, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        print(f"\n[{i + 1}] {spec.name} (v{spec.version})")
        print(f"    Description: {spec.description[:80]}")
        print(f"    Signal rules: {len(spec.signal_rules)}")
        print(f"    Filters: {len(spec.filters)}")
        print(f"    Exit rules: {len(spec.exit_rules)}")
        print(f"    Spec: {spec_path}")
        print(f"    Trace: {trace_path}")

    print(f"\n{'=' * 60}")
    print(f"All specs saved to: {output_dir}")


if __name__ == "__main__":
    main()
