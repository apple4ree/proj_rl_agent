"""
signal_norm.py
--------------
Signal normalization utilities for Layer 1.

Transforms raw alpha scores into a consistent [-1, +1] range using
one of several statistical normalization methods.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np
import pandas as pd


class SignalNormalizer:
    """
    Normalize raw signal scores to a consistent scale.

    Supported methods
    -----------------
    'zscore'
        (x - rolling_mean) / rolling_std, clipped to ±clip_std, then
        divided by clip_std to land in [-1, 1].
    'rank'
        Percentile rank within a rolling window, mapped linearly to [-1, +1].
    'minmax'
        (x - rolling_min) / (rolling_max - rolling_min) → [0, 1],
        then shifted to [-1, +1] as 2*val - 1.
    'robust'
        (x - rolling_median) / rolling_IQR, then clipped to ±clip_std
        and divided by clip_std.

    매개변수
    ----------
    method : str
        Normalization method.  One of 'zscore', 'rank', 'minmax', 'robust'.
    window : int
        Rolling window size used for fitting parameters.
    clip_std : float
        Number of standard deviations to clip at (applies to 'zscore' and
        'robust' methods).
    """

    _VALID_METHODS = {"zscore", "rank", "minmax", "robust"}

    def __init__(
        self,
        method: str = "zscore",
        window: int = 252,
        clip_std: float = 3.0,
    ) -> None:
        if method not in self._VALID_METHODS:
            raise ValueError(
                f"Unknown method {method!r}. Choose from {sorted(self._VALID_METHODS)}."
            )
        self._method = method
        self._window = window
        self._clip_std = clip_std

        # Fitted parameters (set by fit())
        self._mean: float = 0.0
        self._std: float = 1.0
        self._min: float = -1.0
        self._max: float = 1.0
        self._median: float = 0.0
        self._iqr: float = 1.0
        self._history: np.ndarray | None = None

        # Rolling buffer for online normalization
        self._buffer: deque[float] = deque(maxlen=window)

    # ------------------------------------------------------------------
    # 배치 인터페이스
    # ------------------------------------------------------------------

    def fit(self, scores: np.ndarray) -> None:
        """
        Compute normalization parameters from historical scores.

        매개변수
        ----------
        scores : np.ndarray
            Array of historical raw signal scores.
        """
        scores = np.asarray(scores, dtype=float)
        if len(scores) == 0:
            return

        # Keep the last `window` samples as history
        self._history = scores[-self._window:]

        self._mean = float(np.mean(self._history))
        self._std = float(np.std(self._history)) or 1.0
        self._min = float(np.min(self._history))
        self._max = float(np.max(self._history))
        self._median = float(np.median(self._history))
        q75, q25 = float(np.percentile(self._history, 75)), float(np.percentile(self._history, 25))
        self._iqr = (q75 - q25) or 1.0

    def transform(self, score: float) -> float:
        """
        Apply the fitted normalization to a single raw score.

        매개변수
        ----------
        score : float
            Raw signal score.

        반환값
        -------
        float
            Normalized score in [-1, +1].
        """
        if self._method == "zscore":
            return self._zscore_single(score, self._mean, self._std)
        elif self._method == "rank":
            if self._history is None or len(self._history) == 0:
                return 0.0
            rank = float(np.sum(self._history <= score)) / len(self._history)
            return float(rank * 2.0 - 1.0)
        elif self._method == "minmax":
            return self._minmax_single(score, self._min, self._max)
        elif self._method == "robust":
            return self._robust_single(score, self._median, self._iqr)
        return 0.0

    def fit_transform(self, scores: np.ndarray) -> np.ndarray:
        """
        Fit on scores and return the normalized array.

        매개변수
        ----------
        scores : np.ndarray

        반환값
        -------
        np.ndarray
            Normalized scores in [-1, +1].
        """
        self.fit(scores)
        return np.array([self.transform(s) for s in scores], dtype=float)

    # ------------------------------------------------------------------
    # 온라인 롤링 정규화
    # ------------------------------------------------------------------

    def rolling_normalize(self, scores: pd.Series) -> pd.Series:
        """
        Apply online rolling normalization to a pd.Series.

        For each observation the normalization parameters are computed
        from the preceding window of observations, so no future information
        is used.

        매개변수
        ----------
        scores : pd.Series
            Raw signal scores indexed by any index.

        반환값
        -------
        pd.Series
            Normalized scores with the same index.
        """
        result = np.full(len(scores), np.nan)
        buf: deque[float] = deque(maxlen=self._window)

        for i, raw in enumerate(scores.values):
            if not np.isfinite(raw):
                buf.append(0.0)
                result[i] = np.nan
                continue

            arr = np.array(buf, dtype=float) if buf else np.array([raw], dtype=float)

            if self._method == "zscore":
                mean = float(np.mean(arr))
                std = float(np.std(arr)) or 1.0
                result[i] = self._zscore_single(raw, mean, std)
            elif self._method == "rank":
                rank = float(np.sum(arr <= raw)) / len(arr)
                result[i] = rank * 2.0 - 1.0
            elif self._method == "minmax":
                mn = float(np.min(arr))
                mx = float(np.max(arr))
                result[i] = self._minmax_single(raw, mn, mx)
            elif self._method == "robust":
                median = float(np.median(arr))
                q75 = float(np.percentile(arr, 75))
                q25 = float(np.percentile(arr, 25))
                iqr = (q75 - q25) or 1.0
                result[i] = self._robust_single(raw, median, iqr)

            buf.append(raw)

        return pd.Series(result, index=scores.index, name=scores.name)

    # ------------------------------------------------------------------
    # 비공개 정규화 도우미
    # ------------------------------------------------------------------

    def _zscore_single(self, x: float, mean: float, std: float) -> float:
        z = (x - mean) / (std or 1.0)
        clipped = max(-self._clip_std, min(self._clip_std, z))
        return clipped / self._clip_std

    def _minmax_single(self, x: float, mn: float, mx: float) -> float:
        rng = mx - mn
        if rng == 0.0:
            return 0.0
        val = (x - mn) / rng  # [0, 1]
        return float(val * 2.0 - 1.0)  # [-1, 1]

    def _robust_single(self, x: float, median: float, iqr: float) -> float:
        z = (x - median) / (iqr or 1.0)
        clipped = max(-self._clip_std, min(self._clip_std, z))
        return clipped / self._clip_std

    # ------------------------------------------------------------------
    # 문자열 표현
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"SignalNormalizer(method={self._method!r}, "
            f"window={self._window}, clip_std={self._clip_std})"
        )
