"""
계층형 백테스트 진입점.

사용법:
    cd /home/dgu/tick/proj_rl_agent

    PYTHONPATH=src python scripts/backtest.py \
        --spec strategies/imbalance_momentum_v1.0.json \
        --symbol 005930 --start-date 20260313
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from layer0_data import DataIngester, MarketStateBuilder
from layer7_validation import (
    BacktestConfig,
    BacktestResult,
    PipelineRunner,
)
from strategy.base import Strategy
from strategy_compiler.compiler import StrategyCompiler
from strategy_specs.schema import StrategySpec

logger = logging.getLogger(__name__)

# Internal defaults
_DEFAULT_DATA_DIR = "/home/dgu/tick/open-trading-api/data/realtime/H0STASP0"
_DEFAULT_RESAMPLE = "1s"
_DEFAULT_TRADE_LOOKBACK = 100
_DEFAULT_OUTPUT_DIR = "outputs/backtests"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run layered tick-data backtests.")
    parser.add_argument("--spec", required=True, help="Path to strategy spec JSON")
    parser.add_argument("--symbol", required=True, help="KRX symbol code, e.g. 005930")
    parser.add_argument("--start-date", required=True, help="Start date YYYYMMDD")
    parser.add_argument("--end-date", default=None, help="End date YYYYMMDD (default: same as start)")
    return parser.parse_args()


def normalize_date_str(value: str) -> str:
    return value.replace("-", "").strip()


def config_date_str(value: str) -> str:
    normalized = normalize_date_str(value)
    return f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:8]}"


def select_dates(data_dir: str | Path, symbol: str, start_date: str, end_date: str | None = None) -> list[str]:
    ingester = DataIngester(data_dir)
    available_dates = ingester.list_dates(symbol)

    start = normalize_date_str(start_date)
    end = normalize_date_str(end_date or start_date)
    selected = [date for date in available_dates if start <= date <= end]

    if not selected:
        raise FileNotFoundError(
            f"No data found for symbol={symbol} in range {start}..{end} under {Path(data_dir)}"
        )
    return selected


def build_states_for_range(
    *,
    data_dir: str | Path,
    symbol: str,
    start_date: str,
    end_date: str | None = None,
    resample_freq: str | None = None,
    trade_lookback: int = 100,
) -> list:
    builder = MarketStateBuilder(
        data_dir=data_dir,
        trade_lookback=trade_lookback,
        resample_freq=resample_freq,
    )

    states = []
    for date in select_dates(data_dir=data_dir, symbol=symbol, start_date=start_date, end_date=end_date):
        states.extend(
            builder.build_states_from_symbol_date(
                symbol=symbol,
                date=date,
                resample_freq=resample_freq,
            )
        )

    if not states:
        raise ValueError(f"No valid MarketState rows built for symbol={symbol}")
    return states


def build_config(args: argparse.Namespace) -> BacktestConfig:
    """Build BacktestConfig from CLI args with internal defaults."""
    end_date_str = args.end_date or args.start_date
    return BacktestConfig(
        symbol=args.symbol,
        start_date=config_date_str(args.start_date),
        end_date=config_date_str(end_date_str),
        initial_cash=1e8,
        seed=42,
        slicing_algo="TWAP",
        placement_style="spread_adaptive",
        latency_ms=1.0,
        fee_model="krx",
        impact_model="linear",
        compute_attribution=True,
    )


def _build_strategy(args: argparse.Namespace) -> Strategy:
    """Compile a strategy from the spec JSON."""
    spec = StrategySpec.load(args.spec)
    return StrategyCompiler.compile(spec)


def run_backtest(args: argparse.Namespace) -> BacktestResult:
    """Run a backtest from CLI arguments."""
    config = build_config(args)
    strategy = _build_strategy(args)

    states = build_states_for_range(
        data_dir=_DEFAULT_DATA_DIR,
        symbol=config.symbol,
        start_date=config.start_date,
        end_date=config.end_date,
        resample_freq=_DEFAULT_RESAMPLE,
        trade_lookback=_DEFAULT_TRADE_LOOKBACK,
    )

    runner = PipelineRunner(
        config=config,
        data_dir=_DEFAULT_DATA_DIR,
        output_dir=_DEFAULT_OUTPUT_DIR,
        strategy=strategy,
    )
    return runner.run(states)


def run_backtest_with_states(
    config: BacktestConfig,
    states: list,
    data_dir: str | Path,
    output_dir: str | Path = "outputs/backtests",
    strategy: Strategy | None = None,
) -> BacktestResult:
    """
    Run a backtest programmatically with pre-built states.

    매개변수
    ----------
    config : BacktestConfig
        Backtest configuration.
    states : list
        List of MarketState objects.
    data_dir : str | Path
        Data directory for H0STASP0 files.
    output_dir : str | Path
        Directory for output artifacts.
    strategy : Strategy
        Strategy instance.

    반환값
    -------
    BacktestResult
    """
    runner = PipelineRunner(
        config=config,
        data_dir=data_dir,
        output_dir=output_dir,
        strategy=strategy,
    )
    return runner.run(states)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = build_config(args)
    symbol = config.symbol
    start_date = config.start_date
    end_date = config.end_date

    print("=" * 72)
    print(f"Layered Backtest | symbol={symbol} | dates={normalize_date_str(start_date)}..{normalize_date_str(end_date)}")
    print("=" * 72)

    states = build_states_for_range(
        data_dir=_DEFAULT_DATA_DIR,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        resample_freq=_DEFAULT_RESAMPLE,
        trade_lookback=_DEFAULT_TRADE_LOOKBACK,
    )

    strategy = _build_strategy(args)

    runner = PipelineRunner(
        config=config,
        data_dir=_DEFAULT_DATA_DIR,
        output_dir=_DEFAULT_OUTPUT_DIR,
        strategy=strategy,
    )
    result = runner.run(states)
    summary = result.summary()

    print(json.dumps(summary, indent=2, sort_keys=True, default=float))
    run_dir = Path(_DEFAULT_OUTPUT_DIR) / result.run_id
    print(f"Saved run artifacts: {run_dir}")


if __name__ == "__main__":
    main()
