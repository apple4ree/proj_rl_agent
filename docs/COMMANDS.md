# 명령어 레퍼런스

전략 생성 및 검증 플랫폼 실행 명령어 모음.

---

## 환경 설정

```bash
cd /home/dgu/tick/proj_rl_agent
export PYTHONPATH=src
```

---

## 전략 생성

```bash
PYTHONPATH=src python scripts/generate_strategy.py \
    --goal "Order imbalance alpha for KRX"
```

### generate_strategy.py 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--goal` | "Generate tick-level alpha strategies for KRX" | 템플릿 선택 키워드 |

내부 기본값: goal에 가장 적합한 전략 1개 생성, `strategies/`에 저장.

---

## 전략 검토

```bash
PYTHONPATH=src python scripts/review_strategy.py \
    strategies/imbalance_momentum_v1.0.json
```

### review_strategy.py 옵션

| 옵션 | 설명 |
|------|------|
| `spec_path` | (필수, 위치 인자) 검토할 Spec JSON 경로 |

---

## 백테스트

### 단일 종목 백테스트

```bash
PYTHONPATH=src python scripts/backtest.py \
    --spec strategies/imbalance_momentum_v1.0.json \
    --symbol 005930 --start-date 20260313
```

### backtest.py 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--spec` | (필수) | Strategy Spec JSON 경로 |
| `--symbol` | (필수) | KRX 종목 코드 |
| `--start-date` | (필수) | 시작 날짜 (YYYYMMDD) |
| `--end-date` | start-date | 종료 날짜 |

내부 기본값: initial_cash=1억, seed=42, TWAP, spread_adaptive, krx 수수료, linear 충격, latency=1ms.

### Universe 백테스트 (전체 종목 × 기본 Latency Sweep)

```bash
PYTHONPATH=src python scripts/backtest_strategy_universe.py \
    --spec strategies/imbalance_momentum_v1.0.json \
    --data-dir /home/dgu/tick/open-trading-api/data/realtime/H0STASP0 \
    --start-date 20260313
```

### backtest_strategy_universe.py 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--spec` | (필수) | Strategy Spec JSON 경로 |
| `--data-dir` | (필수) | H0STASP0 데이터 디렉토리 |
| `--start-date` | (필수) | 시작 날짜 (YYYYMMDD) |
| `--end-date` | start-date | 종료 날짜 |

내부 기본값: 전체 종목, latency sweep [0,50,100,500,1000]ms, 1s resample, initial_cash=1억, seed=42.

---

## 결과 요약

```bash
PYTHONPATH=src python scripts/summarize_universe_results.py \
    --results outputs/universe_backtest/imbalance_momentum/universe_results.csv
```

### summarize_universe_results.py 옵션

| 옵션 | 설명 |
|------|------|
| `--results` | (필수) universe_results.csv 경로 |

내부 기본값: latency_ms 기준 그룹핑, 메트릭은 net_pnl/sharpe_ratio/max_drawdown/fill_rate.

---

## 권장 워크플로우

```bash
# 1. 전략 생성
PYTHONPATH=src python scripts/generate_strategy.py --goal "Your idea"

# 2. 전략 검토
PYTHONPATH=src python scripts/review_strategy.py \
    strategies/your_strategy_v1.0.json

# 3. 단일 종목 빠른 테스트
PYTHONPATH=src python scripts/backtest.py \
    --spec strategies/your_strategy_v1.0.json \
    --symbol 005930 --start-date 20260313

# 4. Universe 백테스트
PYTHONPATH=src python scripts/backtest_strategy_universe.py \
    --spec strategies/your_strategy_v1.0.json \
    --data-dir /home/dgu/tick/open-trading-api/data/realtime/H0STASP0 \
    --start-date 20260313

# 5. 결과 요약
PYTHONPATH=src python scripts/summarize_universe_results.py \
    --results outputs/universe_backtest/your_strategy/universe_results.csv
```

---

## 테스트

```bash
# 전체 테스트
PYTHONPATH=src python -m pytest tests/ -q

# 특정 모듈
PYTHONPATH=src python -m pytest tests/test_pipeline_runner.py -v
PYTHONPATH=src python -m pytest tests/test_strategy_compiler.py -v
```

---

## 데이터 수집

```bash
PYTHONPATH=src python scripts/collect_data.py --symbol 005930
```

---

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `PYTHONPATH` | 소스 경로 | `src` |
| `KIS_APP_KEY` | KIS API 키 | - |
| `KIS_APP_SECRET` | KIS API 시크릿 | - |
