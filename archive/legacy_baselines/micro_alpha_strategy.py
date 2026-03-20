from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from layer1_signal import (
    ConfidenceEstimator,
    EWMAlpha,
    MicroAlpha,
    OrderFlowAlpha,
    RegimeDetector,
    SignalGate,
    SignalNormalizer,
)

from .base import Strategy

if TYPE_CHECKING:
    from layer0_data.market_state import MarketState


class MicroAlphaStrategy(Strategy):
    """Default tick-level strategy based on the existing Layer 1 alpha stack."""

    def __init__(
        self,
        alpha_model: MicroAlpha | None = None,
        regime_detector: RegimeDetector | None = None,
        confidence_estimator: ConfidenceEstimator | None = None,
        signal_gate: SignalGate | None = None,
        signal_normalizer: SignalNormalizer | None = None,
        normalization_window: int = 64,
    ) -> None:
        self._alpha_model = alpha_model or MicroAlpha(
            models=[
                EWMAlpha(fast_span=5, slow_span=20),
                OrderFlowAlpha(imbalance_threshold=0.1, window=5),
            ],
            weights=[0.4, 0.6],
        )
        self._regime_detector = regime_detector or RegimeDetector()
        self._confidence_estimator = confidence_estimator or ConfidenceEstimator(
            min_history=5,
            entropy_weight=0.2,
        )
        self._signal_gate = signal_gate or SignalGate(
            min_confidence=0.05,
            min_score_abs=0.05,
        )
        self._signal_normalizer = signal_normalizer or SignalNormalizer(
            method="robust",
            window=normalization_window,
            clip_std=3.0,
        )
        self._normalization_window = normalization_window
        self._signal_history: dict[str, list[float]] = {}

    @property
    def name(self) -> str:
        return "MicroAlphaStrategy"

    def reset(self) -> None:
        self._signal_history.clear()
        for component in (
            self._alpha_model,
            self._regime_detector,
            self._confidence_estimator,
            self._signal_gate,
            self._signal_normalizer,
        ):
            reset_fn = getattr(component, "reset", None)
            if callable(reset_fn):
                reset_fn()

    def generate_signal(self, state: "MarketState"):
        if state.lob.mid_price is None:
            return None

        history = self._signal_history.setdefault(state.symbol, [])
        regime = self._regime_detector.detect(state)
        raw_signal = self._alpha_model.predict(state)

        history.append(raw_signal.score)
        hist_arr = np.asarray(history[-self._normalization_window :], dtype=float)
        if len(hist_arr) < 5:
            normalized_score = raw_signal.score
        else:
            self._signal_normalizer.fit(hist_arr)
            normalized_score = self._signal_normalizer.transform(raw_signal.score)

        confidence = self._confidence_estimator.estimate(history[-self._normalization_window :], regime)
        if confidence == 0.0:
            confidence = min(1.0, abs(raw_signal.score))

        # Recompute expected_return from the normalized score so that the
        # sign stays consistent with score (same 10 bps scaling as MicroAlpha).
        expected_return = normalized_score * 10.0

        signal = raw_signal.__class__(
            timestamp=raw_signal.timestamp,
            symbol=raw_signal.symbol,
            score=normalized_score,
            expected_return=expected_return,
            confidence=confidence,
            horizon_steps=raw_signal.horizon_steps,
            tags={
                **raw_signal.tags,
                "session": state.session,
                "regime_vol": regime.vol_regime.name,
                "regime_trend": regime.trend_regime.name,
                "regime_liquidity": regime.liquidity_regime.name,
                "strategy": self.name,
            },
            is_valid=raw_signal.is_valid,
        )

        if not self._signal_gate.passes(signal, regime):
            return None
        return signal
