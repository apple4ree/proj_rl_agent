"""
regime.py
---------
Regime detection for Layer 1.

클래스
-------
RegimeType        - Enum of market regime categories
RegimeContext     - Dataclass capturing current multi-dimensional regime
RegimeDetector    - Stateful detector that classifies regime from MarketState
"""
from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from layer0_data.market_state import MarketState


# ---------------------------------------------------------------------------
# 레짐 유형 분류
# ---------------------------------------------------------------------------

class RegimeType(Enum):
    """Categorical market regime labels."""
    LOW_VOL = auto()
    HIGH_VOL = auto()
    TRENDING_UP = auto()
    TRENDING_DOWN = auto()
    MEAN_REVERTING = auto()
    ILLIQUID = auto()
    OPENING = auto()
    CLOSING = auto()


# ---------------------------------------------------------------------------
# 레짐 컨텍스트 스냅샷
# ---------------------------------------------------------------------------

@dataclass
class RegimeContext:
    """
    Multi-dimensional regime snapshot at a given point in time.

    속성
    ----------
    timestamp : pd.Timestamp
    vol_regime : RegimeType
        Volatility dimension (LOW_VOL or HIGH_VOL).
    trend_regime : RegimeType
        Directional dimension (TRENDING_UP / TRENDING_DOWN / MEAN_REVERTING).
    liquidity_regime : RegimeType
        Liquidity dimension (ILLIQUID or LOW_VOL as proxy for liquid).
    event_tags : list[str]
        Free-text tags such as 'market_open', 'pre_close', 'halted'.
    """

    timestamp: pd.Timestamp
    vol_regime: RegimeType
    trend_regime: RegimeType
    liquidity_regime: RegimeType
    event_tags: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def is_opening(self) -> bool:
        """True if the snapshot is within 30 minutes of the market open."""
        return "market_open" in self.event_tags or RegimeType.OPENING in (
            self.vol_regime,
            self.trend_regime,
            self.liquidity_regime,
        )

    def is_closing(self) -> bool:
        """True if the snapshot is within 30 minutes of the market close."""
        return "pre_close" in self.event_tags or RegimeType.CLOSING in (
            self.vol_regime,
            self.trend_regime,
            self.liquidity_regime,
        )

    def __repr__(self) -> str:
        return (
            f"RegimeContext(ts={self.timestamp}, "
            f"vol={self.vol_regime.name}, "
            f"trend={self.trend_regime.name}, "
            f"liq={self.liquidity_regime.name}, "
            f"tags={self.event_tags})"
        )


# ---------------------------------------------------------------------------
# Regime detector
# ---------------------------------------------------------------------------

class RegimeDetector:
    """
    Stateful market regime detector.

    Maintains rolling buffers of mid-prices, spreads, and volumes to
    continuously classify the prevailing 변동성, trend, and liquidity
    regimes.

    매개변수
    ----------
    vol_window : int
        Number of observations used to estimate rolling realised 변동성.
    trend_window : int
        Number of observations for trend momentum detection.
    liquidity_window : int
        Number of observations for spread / depth-based liquidity assessment.
    vol_high_threshold : float
        Annualised-vol threshold (in percent) above which HIGH_VOL is declared.
    spread_illiquid_bps : float
        Spread in bps above which ILLIQUID is declared.
    """

    _OPENING_WINDOW_MIN: int = 30
    _CLOSING_WINDOW_MIN: int = 30

    # Typical KRX session boundaries (UTC+9)
    _OPEN_HOUR: int = 9
    _OPEN_MINUTE: int = 0
    _CLOSE_HOUR: int = 15
    _CLOSE_MINUTE: int = 30

    def __init__(
        self,
        vol_window: int = 60,
        trend_window: int = 20,
        liquidity_window: int = 30,
        vol_high_threshold: float = 0.25,
        spread_illiquid_bps: float = 50.0,
    ) -> None:
        self._vol_window = vol_window
        self._trend_window = trend_window
        self._liquidity_window = liquidity_window
        self._vol_high_threshold = vol_high_threshold
        self._spread_illiquid_bps = spread_illiquid_bps

        # 롤링 버퍼
        self._mid_prices: deque[float] = deque(maxlen=max(vol_window, trend_window))
        self._spreads_bps: deque[float] = deque(maxlen=liquidity_window)
        self._volumes: deque[float] = deque(maxlen=liquidity_window)
        self._timestamps: deque[pd.Timestamp] = deque(maxlen=2)

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    def update(self, state: MarketState) -> None:
        """
        Ingest a new market state observation into the rolling buffers.

        매개변수
        ----------
        state : MarketState
            Latest market snapshot.
        """
        mid = state.lob.mid_price
        if mid is not None:
            self._mid_prices.append(mid)

        spread_bps = state.lob.spread_bps
        if spread_bps is not None:
            self._spreads_bps.append(spread_bps)

        # Volume: use total bid depth as proxy when trade data is unavailable
        if state.trades is not None and not state.trades.empty and "volume" in state.trades.columns:
            total_vol = float(state.trades["volume"].sum())
        else:
            total_vol = float(state.lob.total_bid_depth + state.lob.total_ask_depth)
        self._volumes.append(total_vol)
        self._timestamps.append(state.timestamp)

    def detect(self, state: MarketState) -> RegimeContext:
        """
        클래스ify the current regime and return a RegimeContext.

        Also calls update() internally so callers only need detect().

        매개변수
        ----------
        state : MarketState

        반환값
        -------
        RegimeContext
        """
        self.update(state)

        vol_regime = self._detect_vol_regime()
        trend_regime = self._detect_trend_regime()
        liq_regime = self._detect_liquidity_regime()
        event_tags = self._detect_event_tags(state)

        return RegimeContext(
            timestamp=state.timestamp,
            vol_regime=vol_regime,
            trend_regime=trend_regime,
            liquidity_regime=liq_regime,
            event_tags=event_tags,
        )

    def reset(self) -> None:
        """Clear all rolling buffers."""
        self._mid_prices.clear()
        self._spreads_bps.clear()
        self._volumes.clear()
        self._timestamps.clear()

    # ------------------------------------------------------------------
    # Internal detection helpers
    # ------------------------------------------------------------------

    def _detect_vol_regime(self) -> RegimeType:
        """
        클래스ify 변동성 regime from rolling realised vol.

        반환값 HIGH_VOL when annualised realised vol exceeds the threshold.
        """
        if len(self._mid_prices) < 2:
            return RegimeType.LOW_VOL

        prices = list(self._mid_prices)
        returns = [
            math.log(prices[i] / prices[i - 1])
            for i in range(1, len(prices))
            if prices[i - 1] > 0
        ]
        if len(returns) < 2:
            return RegimeType.LOW_VOL

        try:
            std_ret = statistics.stdev(returns)
        except statistics.StatisticsError:
            return RegimeType.LOW_VOL

        # Rough annualisation: assume ~252 trading days, ~390 ticks/day
        annualised_vol = std_ret * math.sqrt(252 * 390)
        return RegimeType.HIGH_VOL if annualised_vol > self._vol_high_threshold else RegimeType.LOW_VOL

    def _detect_trend_regime(self) -> RegimeType:
        """
        클래스ify trend regime from price momentum.

        Uses a simple comparison of first half vs second half mean price
        over the trend window.
        """
        if len(self._mid_prices) < max(4, self._trend_window // 2):
            return RegimeType.MEAN_REVERTING

        prices = list(self._mid_prices)[-self._trend_window:]
        half = len(prices) // 2
        if half == 0:
            return RegimeType.MEAN_REVERTING

        first_half_mean = sum(prices[:half]) / half
        second_half_mean = sum(prices[half:]) / (len(prices) - half)

        if first_half_mean == 0.0:
            return RegimeType.MEAN_REVERTING

        momentum = (second_half_mean - first_half_mean) / first_half_mean

        # 임계값: 0.05% move in the window counts as trending
        trend_threshold = 0.0005
        if momentum > trend_threshold:
            return RegimeType.TRENDING_UP
        elif momentum < -trend_threshold:
            return RegimeType.TRENDING_DOWN
        return RegimeType.MEAN_REVERTING

    def _detect_liquidity_regime(self) -> RegimeType:
        """
        클래스ify liquidity regime from spread and depth.

        반환값 ILLIQUID when spread is persistently wide, otherwise LOW_VOL
        as a proxy for a liquid, normal market.
        """
        if not self._spreads_bps:
            return RegimeType.LOW_VOL

        avg_spread = sum(self._spreads_bps) / len(self._spreads_bps)
        return (
            RegimeType.ILLIQUID
            if avg_spread > self._spread_illiquid_bps
            else RegimeType.LOW_VOL
        )

    def _detect_event_tags(self, state: MarketState) -> list[str]:
        """
        Derive session event tags from the state timestamp.

        Tags: 'market_open', 'pre_close', 'halted', 'after_hours'
        """
        tags: list[str] = []
        ts = state.timestamp

        # Session tags from MarketState.session field
        if state.session == "halted":
            tags.append("halted")
        elif state.session in ("pre", "post", "closed"):
            tags.append("after_hours")

        # Time-of-day proximity tags (assumes tz-aware or naive UTC+9 equivalent)
        try:
            hour = ts.hour
            minute = ts.minute
            total_minutes = hour * 60 + minute

            open_minutes = self._OPEN_HOUR * 60 + self._OPEN_MINUTE
            close_minutes = self._CLOSE_HOUR * 60 + self._CLOSE_MINUTE

            if 0 <= total_minutes - open_minutes <= self._OPENING_WINDOW_MIN:
                tags.append("market_open")
            if 0 <= close_minutes - total_minutes <= self._CLOSING_WINDOW_MIN:
                tags.append("pre_close")
        except (AttributeError, TypeError):
            pass

        return tags
