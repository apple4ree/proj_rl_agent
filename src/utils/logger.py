"""
실험 로거 - 학습과 평가를 위한 구조화 로깅.

제공 기능:
    * ``ExperimentLogger``  - 에피소드, 학습 통계 기록 및 JSON/CSV 저장
    * 콘솔 + 파일 로깅(레벨 설정 가능)
    * SB3 기반 선택적 TensorBoard 연동
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def setup_logging(
    log_dir: str | Path = "logs",
    level: str = "INFO",
    name: str = "lob-exec",
) -> logging.Logger:
    """콘솔 + 파일 핸들러를 갖는 프로젝트 공용 로거를 구성한다.

    매개변수
    ----------
    log_dir : str | Path
        로그 파일을 저장할 디렉터리.
    level : str
        로깅 레벨(DEBUG, INFO, WARNING, ERROR).
    name : str
        로거 이름.

    반환값
    -------
    logging.Logger
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(
        log_dir / f"{name}_{timestamp}.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


class ExperimentLogger:
    """학습과 평가 실행을 위한 구조화된 실험 로거.

    에피소드별 지표와 하이퍼파라미터를 추적하고, 결과를 이후 분석을 위해
    JSON과 CSV 파일로 기록한다.

    매개변수
    ----------
    experiment_name : str
        실험 이름(파일명에 사용됨).
    log_dir : str | Path
        출력 디렉터리.
    config : dict | None
        기록할 하이퍼파라미터/설정.
    """

    def __init__(
        self,
        experiment_name: str = "experiment",
        log_dir: str | Path = "logs",
        config: dict[str, Any] | None = None,
    ):
        self.experiment_name = experiment_name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.config = config or {}
        self.episodes: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {
            "experiment_name": experiment_name,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "config": self.config,
        }

        self._logger = setup_logging(self.log_dir, name=experiment_name)
        self._csv_path = self.log_dir / f"{experiment_name}_episodes.csv"
        self._csv_header_written = False

    def log_episode(
        self,
        episode: int,
        agent_name: str,
        is_bps: float,
        total_reward: float,
        remaining_shares: int = 0,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Log a single episode result.

        매개변수
        ----------
        episode : int
            Episode number.
        agent_name : str
            Name of the agent.
        is_bps : float
            Implementation Shortfall in basis points.
        total_reward : float
            Cumulative episode reward.
        remaining_shares : int
            Unexecuted shares at episode end.
        extra : dict | None
            Additional fields to log.
        """
        record = {
            "episode": episode,
            "agent": agent_name,
            "is_bps": round(is_bps, 4),
            "total_reward": round(total_reward, 4),
            "remaining_shares": remaining_shares,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            record.update(extra)

        self.episodes.append(record)
        self._append_csv(record)

    def log_message(self, msg: str, level: str = "info") -> None:
        """Log a free-form message."""
        getattr(self._logger, level.lower(), self._logger.info)(msg)

    def log_training_step(
        self,
        timesteps: int,
        mean_reward: float,
        mean_is: float,
        **kwargs: Any,
    ) -> None:
        """Log a training checkpoint."""
        self._logger.info(
            "Timesteps: %d | Mean Reward: %.1f | Mean IS: %.2f bps%s",
            timesteps,
            mean_reward,
            mean_is,
            "".join(f" | {k}: {v}" for k, v in kwargs.items()),
        )

    def save_json(self, filename: str | None = None) -> Path:
        """Save all logged data to a JSON file.

        반환값
        -------
        Path
            Path to the saved JSON file.
        """
        filename = filename or f"{self.experiment_name}_results.json"
        path = self.log_dir / filename

        self.metadata["end_time"] = datetime.now(timezone.utc).isoformat()
        self.metadata["n_episodes"] = len(self.episodes)

        data = {
            "metadata": self.metadata,
            "episodes": self.episodes,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self._logger.info("Results saved: %s (%d episodes)", path, len(self.episodes))
        return path

    def _append_csv(self, record: dict[str, Any]) -> None:
        """Append a single record to the CSV file."""
        is_new = not self._csv_header_written

        with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(record.keys()))
            if is_new:
                writer.writeheader()
                self._csv_header_written = True
            writer.writerow(record)
