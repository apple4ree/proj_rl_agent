"""
confidence.py
-------------
Confidence estimation and signal gating for Layer 1.

클래스
-------
ConfidenceEstimator  - Estimates prediction quality of a batch of signals
SignalGate           - Filters Signal objects based on quality thresholds
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .regime import RegimeContext
    from .signal import Signal


# ---------------------------------------------------------------------------
# Confidence estimator
# ---------------------------------------------------------------------------

class ConfidenceEstimator:
    """
    Estimates signal confidence from a history of recent signal scores.

    Confidence is a composite of:
    1. Signal consistency  - low standard deviation among recent scores.
    2. Signal magnitude    - stronger signals are more confident.
    3. Regime familiarity  - confidence is dampened during transitions.

    매개변수
    ----------
    min_history : int
        Minimum number of historical scores required to compute confidence.
        반환값 0.0 if fewer samples are available.
    entropy_weight : float
        Weight of the entropy penalty in [0, 1].  Higher values penalise
        high-entropy (random-looking) signal histories more strongly.
    """

    _N_BINS: int = 5  # Number of bins for signal discretisation

    def __init__(
        self,
        min_history: int = 20,
        entropy_weight: float = 0.3,
    ) -> None:
        self._min_history = min_history
        self._entropy_weight = float(entropy_weight)

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    def estimate(
        self,
        signal_scores: list[float],
        regime: RegimeContext,
    ) -> float:
        """
        Compute confidence score in [0, 1].

        매개변수
        ----------
        signal_scores : list[float]
            Recent signal score history (most recent last).
        regime : RegimeContext
            Current regime snapshot for multiplier adjustment.

        반환값
        -------
        float
            Confidence in [0, 1].  반환값 0.0 when history is too short.
        """
        if len(signal_scores) < self._min_history:
            return 0.0

        # 1. Magnitude component: mean absolute score
        mean_abs = sum(abs(s) for s in signal_scores) / len(signal_scores)

        # 2. Consistency component: 1 - normalised standard deviation
        mean_val = sum(signal_scores) / len(signal_scores)
        variance = sum((s - mean_val) ** 2 for s in signal_scores) / len(signal_scores)
        std = math.sqrt(variance)
        consistency = max(0.0, 1.0 - std)  # std in [-1,1] range is at most 2; keep clipped

        # 3. Entropy penalty
        entropy = self._signal_entropy(signal_scores)
        max_entropy = math.log2(self._N_BINS) if self._N_BINS > 1 else 1.0
        normalised_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
        entropy_penalty = self._entropy_weight * normalised_entropy

        # Combine
        raw_confidence = mean_abs * consistency * (1.0 - entropy_penalty)

        # 4. Regime multiplier
        regime_mult = self._regime_multiplier(regime)
        confidence = raw_confidence * regime_mult

        return float(max(0.0, min(1.0, confidence)))

    # ------------------------------------------------------------------
    # 내부 도우미
    # ------------------------------------------------------------------

    @staticmethod
    def _signal_entropy(scores: list[float]) -> float:
        """
        Compute the Shannon entropy of a discretised signal distribution.

        Scores in [-1, 1] are binned into _N_BINS equal-width bins.

        반환값
        -------
        float
            Entropy in bits.
        """
        n_bins = ConfidenceEstimator._N_BINS
        bin_width = 2.0 / n_bins  # bins cover [-1, 1]
        counts = [0] * n_bins
        for s in scores:
            idx = int((s + 1.0) / bin_width)
            idx = max(0, min(n_bins - 1, idx))
            counts[idx] += 1

        total = len(scores)
        if total == 0:
            return 0.0

        entropy = 0.0
        for c in counts:
            if c > 0:
                p = c / total
                entropy -= p * math.log2(p)
        return entropy

    @staticmethod
    def _regime_multiplier(regime: RegimeContext) -> float:
        """
        Return a confidence multiplier based on regime characteristics.

        Dampens confidence during high-변동성, illiquid, or session-edge
        conditions where signal quality is typically lower.

        반환값
        -------
        float
            Multiplier in (0, 1].
        """
        from .regime import RegimeType

        mult = 1.0

        if regime.vol_regime == RegimeType.HIGH_VOL:
            mult *= 0.7
        if regime.liquidity_regime == RegimeType.ILLIQUID:
            mult *= 0.5
        if "market_open" in regime.event_tags:
            mult *= 0.6
        if "pre_close" in regime.event_tags:
            mult *= 0.75
        if "halted" in regime.event_tags:
            mult *= 0.0

        return float(max(0.0, min(1.0, mult)))


# ---------------------------------------------------------------------------
# Signal gate
# ---------------------------------------------------------------------------

class SignalGate:
    """
    Filters Signal objects against configurable quality thresholds.

    매개변수
    ----------
    min_confidence : float
        Minimum confidence level for a signal to pass (default 0.3).
    min_score_abs : float
        Minimum absolute score for a signal to pass (default 0.1).
    allowed_sessions : list[str] | None
        Whitelist of allowed session strings.  None means all sessions pass.
        E.g. ['regular'] to only trade in regular hours.
    """

    def __init__(
        self,
        min_confidence: float = 0.3,
        min_score_abs: float = 0.1,
        allowed_sessions: list[str] | None = None,
    ) -> None:
        self._min_confidence = min_confidence
        self._min_score_abs = min_score_abs
        self._allowed_sessions = allowed_sessions

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    def passes(self, signal: Signal, regime: RegimeContext) -> bool:
        """
        Return True when the signal passes all quality gates.

        Checks
        ------
        1. signal.is_valid
        2. abs(signal.score) >= min_score_abs
        3. signal.confidence >= min_confidence
        4. Session allowed (if session restriction configured)
        5. Market not halted
        """
        if not signal.is_valid:
            return False
        if abs(signal.score) < self._min_score_abs:
            return False
        if signal.confidence < self._min_confidence:
            return False
        if "halted" in regime.event_tags:
            return False

        # 레짐 태그 기반 세션 점검
        if self._allowed_sessions is not None:
            session = signal.tags.get("session", "regular")
            if session not in self._allowed_sessions:
                return False

        return True

    def filter(
        self,
        signals: list[Signal],
        regime: RegimeContext,
    ) -> list[Signal]:
        """
        Return only signals that pass all quality gates.

        매개변수
        ----------
        signals : list[Signal]
        regime : RegimeContext

        반환값
        -------
        list[Signal]
            Subset of input signals that pass.
        """
        return [s for s in signals if self.passes(s, regime)]
