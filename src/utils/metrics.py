"""
에이전트 성능 평가용 체결 지표.

Provides:
    * ``compute_episode_metrics``  — per-episode summary from execution log
    * ``compute_aggregate_metrics`` — multi-episode statistics
    * ``compare_agents``           — side-by-side agent comparison table
    * ``sharpe_ratio``             — risk-adjusted reward metric
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class EpisodeMetrics:
    """Metrics for a single episode."""

    is_bps: float = 0.0               # Implementation Shortfall in bps
    vwap: float = 0.0                 # Volume-Weighted Average Price
    total_reward: float = 0.0
    total_executed: int = 0
    remaining_shares: int = 0
    arrival_price: float = 0.0
    completion_rate: float = 0.0      # fraction executed
    n_trades: int = 0                 # number of non-zero trades
    avg_trade_size: float = 0.0
    max_single_trade_frac: float = 0.0  # largest trade / total_shares


@dataclass
class AggregateMetrics:
    """Aggregated metrics over multiple episodes."""

    n_episodes: int = 0
    is_mean: float = 0.0
    is_std: float = 0.0
    is_median: float = 0.0
    is_iqm: float = 0.0               # interquartile mean
    reward_mean: float = 0.0
    reward_std: float = 0.0
    completion_rate: float = 0.0
    sharpe: float = 0.0               # reward Sharpe ratio


def compute_episode_metrics(info: dict, total_reward: float) -> EpisodeMetrics:
    """Compute metrics from a single episode's final info dict.

    매개변수
    ----------
    info : dict
        The ``info`` dict returned by ``env.step()`` at episode end.
    total_reward : float
        Cumulative reward over the episode.

    반환값
    -------
    EpisodeMetrics
    """
    total_shares = info.get("remaining_shares", 0) + info.get("total_executed", 0)
    exec_log = info.get("execution_log", [])

    trade_sizes = [e["trade_size"] for e in exec_log]
    n_trades = sum(1 for s in trade_sizes if s > 0)

    return EpisodeMetrics(
        is_bps=info.get("is_bps", 0.0),
        vwap=info.get("vwap", 0.0),
        total_reward=total_reward,
        total_executed=info.get("total_executed", 0),
        remaining_shares=info.get("remaining_shares", 0),
        arrival_price=info.get("arrival_price", 0.0),
        completion_rate=info.get("total_executed", 0) / max(total_shares, 1),
        n_trades=n_trades,
        avg_trade_size=np.mean(trade_sizes) if trade_sizes else 0.0,
        max_single_trade_frac=(
            max(trade_sizes) / max(total_shares, 1) if trade_sizes else 0.0
        ),
    )


def compute_aggregate_metrics(
    episode_metrics: list[EpisodeMetrics],
) -> AggregateMetrics:
    """Aggregate metrics over multiple episodes.

    매개변수
    ----------
    episode_metrics : list[EpisodeMetrics]
        Results from ``compute_episode_metrics`` for each episode.

    반환값
    -------
    AggregateMetrics
    """
    if not episode_metrics:
        return AggregateMetrics()

    is_vals = np.array([m.is_bps for m in episode_metrics])
    rewards = np.array([m.total_reward for m in episode_metrics])
    completions = np.array([m.completion_rate for m in episode_metrics])

    return AggregateMetrics(
        n_episodes=len(episode_metrics),
        is_mean=float(np.mean(is_vals)),
        is_std=float(np.std(is_vals)),
        is_median=float(np.median(is_vals)),
        is_iqm=float(_interquartile_mean(is_vals)),
        reward_mean=float(np.mean(rewards)),
        reward_std=float(np.std(rewards)),
        completion_rate=float(np.mean(completions)),
        sharpe=float(sharpe_ratio(rewards)),
    )


def sharpe_ratio(rewards: np.ndarray) -> float:
    """Compute Sharpe ratio of episode rewards.

    ``SR = mean(rewards) / std(rewards)``

    매개변수
    ----------
    rewards : np.ndarray
        Array of per-episode total rewards.

    반환값
    -------
    float
        Sharpe ratio (0 if std is zero).
    """
    if len(rewards) < 2:
        return 0.0
    std = float(np.std(rewards))
    if std < 1e-12:
        return 0.0
    return float(np.mean(rewards)) / std


def _interquartile_mean(values: np.ndarray) -> float:
    """Compute interquartile mean (IQM), excluding bottom/top 25%.

    Robust to outliers — recommended by rliable for evaluation.
    """
    if len(values) < 4:
        return float(np.mean(values))
    q25 = float(np.percentile(values, 25))
    q75 = float(np.percentile(values, 75))
    mask = (values >= q25) & (values <= q75)
    if not np.any(mask):
        return float(np.mean(values))
    return float(np.mean(values[mask]))


def compare_agents(
    results: dict[str, list[EpisodeMetrics]],
) -> str:
    """Format a comparison table across agents.

    매개변수
    ----------
    results : dict[str, list[EpisodeMetrics]]
        ``{agent_name: [EpisodeMetrics, ...]}``.

    반환값
    -------
    str
        Formatted ASCII table.
    """
    lines = []
    header = (
        f"  {'Agent':22s} | "
        f"{'IS (bps)':>14s} | "
        f"{'Reward':>20s} | "
        f"{'Sharpe':>7s} | "
        f"{'Complete':>8s}"
    )
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    for name, episodes in results.items():
        agg = compute_aggregate_metrics(episodes)
        lines.append(
            f"  {name:22s} | "
            f"{agg.is_mean:7.2f} ± {agg.is_std:5.2f} | "
            f"{agg.reward_mean:10.1f} ± {agg.reward_std:7.1f} | "
            f"{agg.sharpe:7.3f} | "
            f"{agg.completion_rate:7.1%}"
        )

    return "\n".join(lines)
