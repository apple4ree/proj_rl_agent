"""
micro_alpha.py
--------------
Microstructure alpha models for Layer 1.

Hierarchy
---------
AlphaModel           - abstract base
  EWMAlpha           - EMA momentum signal
  OrderFlowAlpha     - order-imbalance signal
  SpreadAlpha        - spread-compression signal

MicroAlpha           - ensemble wrapper → produces Signal
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import deque
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from layer0_data.market_state import MarketState

from .signal import Signal


# ---------------------------------------------------------------------------
# 추상 기반
# ---------------------------------------------------------------------------

class AlphaModel(ABC):
    """추상 기반 class for a single-factor alpha model."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable model identifier."""

    @abstractmethod
    def predict(self, state: MarketState) -> float:
        """
        Generate a raw alpha score in [-1, +1].

        매개변수
        ----------
        state : MarketState
            Current market snapshot.

        반환값
        -------
        float
            Alpha score. Positive = bullish, negative = bearish.
        """

    def reset(self) -> None:
        """Reset any internal state (e.g. rolling buffers)."""


# ---------------------------------------------------------------------------
# EWM 모멘텀 알파
# ---------------------------------------------------------------------------

class EWMAlpha(AlphaModel):
    """
    Exponentially-weighted momentum signal.

    Computes the ratio fast_ema / slow_ema - 1 on mid-price returns and
    maps the result to [-1, +1] via a soft-clamp (tanh).

    매개변수
    ----------
    fast_span : int
        Span for the fast EMA (default 5).
    slow_span : int
        Span for the slow EMA (default 20).
    """

    def __init__(self, fast_span: int = 5, slow_span: int = 20) -> None:
        if fast_span >= slow_span:
            raise ValueError("fast_span must be strictly less than slow_span")
        self._fast_span = fast_span
        self._slow_span = slow_span
        self._fast_alpha = 2.0 / (fast_span + 1)
        self._slow_alpha = 2.0 / (slow_span + 1)
        self._fast_ema: float | None = None
        self._slow_ema: float | None = None
        self._prev_mid: float | None = None
        self._last_ts: pd.Timestamp | None = None

    @property
    def name(self) -> str:
        return f"EWMAlpha(fast={self._fast_span}, slow={self._slow_span})"

    def update(self, mid_price: float, timestamp: pd.Timestamp) -> None:
        """
        Advance the internal EMA state with a new mid-price observation.

        매개변수
        ----------
        mid_price : float
            Current mid-price.
        timestamp : pd.Timestamp
            Observation timestamp (stored for bookkeeping).
        """
        if self._fast_ema is None:
            self._fast_ema = mid_price
            self._slow_ema = mid_price
        else:
            self._fast_ema = (
                self._fast_alpha * mid_price + (1 - self._fast_alpha) * self._fast_ema
            )
            self._slow_ema = (
                self._slow_alpha * mid_price + (1 - self._slow_alpha) * self._slow_ema
            )
        self._prev_mid = mid_price
        self._last_ts = timestamp

    def predict(self, state: MarketState) -> float:
        """
        Return the EWM momentum signal for the given market state.

        Also updates internal EMAs from the state's mid-price before
        computing the signal, so callers only need to call predict().

        반환값
        -------
        float
            Score in [-1, +1].
        """
        mid = state.lob.mid_price
        if mid is None:
            return 0.0
        self.update(mid, state.timestamp)
        if self._fast_ema is None or self._slow_ema is None or self._slow_ema == 0.0:
            return 0.0
        raw = self._fast_ema / self._slow_ema - 1.0
        # 스케일 계수를 둔 tanh로 [-1, 1] 범위에 부드럽게 제한
        return float(math.tanh(raw * 100))

    def reset(self) -> None:
        """Reset all internal EMA state."""
        self._fast_ema = None
        self._slow_ema = None
        self._prev_mid = None
        self._last_ts = None


# ---------------------------------------------------------------------------
# 주문 흐름/불균형 알파
# ---------------------------------------------------------------------------

class OrderFlowAlpha(AlphaModel):
    """
    Order-book imbalance signal.

    A persistent positive imbalance (more bid depth than ask depth)
    predicts upward price pressure and generates a buy signal.

    매개변수
    ----------
    imbalance_threshold : float
        Magnitude above which a raw imbalance is considered significant.
    window : int
        Rolling window size for smoothing imbalances.
    """

    def __init__(
        self,
        imbalance_threshold: float = 0.2,
        window: int = 5,
    ) -> None:
        self._threshold = imbalance_threshold
        self._window = window
        self._buffer: deque[float] = deque(maxlen=window)

    @property
    def name(self) -> str:
        return f"OrderFlowAlpha(thr={self._threshold}, w={self._window})"

    def predict(self, state: MarketState) -> float:
        """
        Compute smoothed order imbalance signal.

        반환값
        -------
        float
            Score in [-1, +1].
        """
        imbalance = state.lob.order_imbalance
        if imbalance is None:
            imbalance = 0.0
        self._buffer.append(imbalance)
        if not self._buffer:
            return 0.0
        smoothed = sum(self._buffer) / len(self._buffer)
        # 임계값 데드밴드를 적용한 뒤 부드럽게 제한
        if abs(smoothed) < self._threshold:
            return 0.0
        return float(math.tanh(smoothed * 3))

    def reset(self) -> None:
        """Clear the rolling imbalance buffer."""
        self._buffer.clear()


# ---------------------------------------------------------------------------
# 스프레드 압축 알파
# ---------------------------------------------------------------------------

class SpreadAlpha(AlphaModel):
    """
    Spread-compression signal.

    A tight spread indicates high liquidity and favourable execution
    conditions (positive score). A wide spread discourages trading
    (negative score).

    The signal is computed relative to a rolling average spread.
    """

    def __init__(self, window: int = 20, wide_spread_bps: float = 30.0) -> None:
        self._window = window
        self._wide_bps = wide_spread_bps
        self._spreads: deque[float] = deque(maxlen=window)

    @property
    def name(self) -> str:
        return f"SpreadAlpha(w={self._window}, wide={self._wide_bps}bps)"

    def predict(self, state: MarketState) -> float:
        """
        Return a score based on relative spread tightness.

        반환값
        -------
        float
            Positive when spread is tight vs. history; negative when wide.
        """
        spread_bps = state.lob.spread_bps
        if spread_bps is None:
            return 0.0
        self._spreads.append(spread_bps)
        avg_spread = sum(self._spreads) / len(self._spreads) if self._spreads else spread_bps
        if avg_spread == 0.0:
            return 0.0
        # Relative tightness: <1 means tighter than average → positive signal
        relative = spread_bps / avg_spread
        # Map: 0 spread → +1, average → 0, wide spread → negative
        score = 1.0 - relative
        # Apply absolute penalty when spread is very wide
        if spread_bps > self._wide_bps:
            penalty = min((spread_bps - self._wide_bps) / self._wide_bps, 1.0)
            score = score - penalty
        return float(max(-1.0, min(1.0, score)))

    def reset(self) -> None:
        self._spreads.clear()


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------

class MicroAlpha:
    """
    Ensemble of alpha models producing a composite Signal.

    Individual model scores are combined via a weighted average and
    packaged into a Signal dataclass.

    매개변수
    ----------
    models : list[AlphaModel]
        Component alpha models.
    weights : list[float] | None
        Relative weights for each model.  Defaults to equal weighting.
    """

    FEATURE_VERSION = "1.0.0"  # EWM(5,20) + OrderFlow(0.2,5) + Spread(20,30)

    def __init__(
        self,
        models: list[AlphaModel],
        weights: list[float] | None = None,
    ) -> None:
        if not models:
            raise ValueError("At least one AlphaModel is required.")
        self._models = models
        if weights is not None:
            if len(weights) != len(models):
                raise ValueError("len(weights) must equal len(models)")
            total = sum(weights)
            self._weights = [w / total for w in weights]
        else:
            n = len(models)
            self._weights = [1.0 / n] * n
        self._horizon_steps: int = 1

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    def update(self, state: MarketState) -> None:
        """
        Push new market state to all sub-models (for models that maintain
        separate update / predict cycles).
        """
        # Most models update lazily inside predict(); this is a no-op hook
        # for models that need an explicit advance step.
        pass

    def predict(self, state: MarketState) -> Signal:
        """
        Compute weighted ensemble score and return a Signal.

        매개변수
        ----------
        state : MarketState
            Current market snapshot.

        반환값
        -------
        Signal
            Composite signal with metadata tags for each model's contribution.
        """
        individual_scores: dict[str, float] = {}
        composite = 0.0
        for model, weight in zip(self._models, self._weights):
            score = model.predict(state)
            individual_scores[model.name] = round(score, 6)
            composite += weight * score

        composite = float(max(-1.0, min(1.0, composite)))

        # Rough expected-return estimate: score * 10 bps (placeholder scaling)
        expected_return = composite * 10.0

        # Simple confidence: mean absolute agreement among models
        if len(individual_scores) > 1:
            scores_list = list(individual_scores.values())
            mean_abs = sum(abs(s) for s in scores_list) / len(scores_list)
            variance = sum((s - composite) ** 2 for s in scores_list) / len(scores_list)
            std = math.sqrt(variance)
            confidence = float(max(0.0, min(1.0, mean_abs * (1.0 - std))))
        else:
            confidence = abs(composite)

        return Signal(
            timestamp=state.timestamp,
            symbol=state.symbol,
            score=composite,
            expected_return=expected_return,
            confidence=confidence,
            horizon_steps=self._horizon_steps,
            tags={
                "alpha_source": "MicroAlpha",
                "model_scores": individual_scores,
            },
            is_valid=True,
        )

    def reset(self) -> None:
        """Reset all sub-models."""
        for model in self._models:
            model.reset()
