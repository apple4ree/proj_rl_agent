# 틱 데이터 전략 생성 및 검증 플랫폼

LOB(호가창) 틱 데이터 기반 **전략 생성 → 검토 → 컴파일 → Universe 백테스트** 플랫폼.

템플릿/규칙 기반으로 전략 사양(Strategy Spec)을 생성하고, 정적 검토를 거친 뒤, 다종목 × 다 latency 조건에서 체계적으로 검증한다.

## 핵심 아키텍처

| 구성요소 | 역할 |
|---------|------|
| **Strategy Generation** | 전략 사양 생성 — template backend (기본) 또는 OpenAI multi-agent backend |
| **Strategy Review** | 정적 규칙 기반 사양 검토 (schema, risk, redundancy, feature 검증) |
| **Strategy Spec** | JSON 기반 전략 명세 (signal, filter, position, exit rules) |
| **Strategy Compiler** | Spec → 실행 가능한 Strategy 객체로 변환 |
| **Universe Backtest** | 모든 적용 가능 종목 × 다양한 latency로 백테스트 |
| **Layer 0~7** | 7계층 백테스팅 파이프라인 |

## 프로젝트 구조

```
proj_rl_agent/
├── src/
│   ├── strategy_generation/   # 전략 생성 (template / OpenAI multi-agent)
│   ├── strategy_review/       # 정적 규칙 기반 전략 검토
│   ├── strategy_specs/        # 전략 사양 스키마
│   ├── strategy_compiler/     # Spec → Strategy 컴파일러
│   ├── strategy_registry/     # 전략 저장·관리
│   ├── strategy/              # Strategy ABC (base.py)
│   ├── layer0_data/           # 데이터 수집·정제·동기화·피처
│   ├── layer1_signal/         # 시그널 데이터 타입
│   ├── layer2_position/       # 포지션 타겟·리스크 관리
│   ├── layer3_order/          # 주문 타입·델타 계산
│   ├── layer4_execution/      # 슬라이싱·배치·타이밍
│   ├── layer5_simulator/      # 체결·수수료·충격·latency
│   ├── layer6_evaluator/      # PnL·리스크·실행 품질
│   └── layer7_validation/     # 백테스트 오케스트레이션
├── scripts/
│   ├── generate_strategy.py          # 전략 사양 생성
│   ├── review_strategy.py            # 전략 사양 검토
│   ├── backtest.py                   # 단일 종목 백테스트
│   ├── backtest_strategy_universe.py # Universe 백테스트
│   ├── summarize_universe_results.py # 결과 집계
│   ├── collect_data.py               # 데이터 수집
│   └── visualize.py                  # 시각화
├── strategies/                # 전략 사양 저장소
├── conf/                      # YAML 설정
├── tests/                     # pytest 테스트
├── docs/                      # 문서
└── archive/                   # 비활성 코드·문서 보관
    ├── legacy_baselines/      # MicroAlphaStrategy 등
    ├── legacy_agents/         # llm_agents/ (LLM 기반 Agent)
    └── docs/                  # 과거 연구 제안서, 모델 명세 등
```

## 빠른 시작

```bash
cd /home/dgu/tick/proj_rl_agent

# 1. 전략 생성 (template backend — 기본)
PYTHONPATH=src python scripts/generate_strategy.py \
    --goal "Order imbalance alpha"

# 1-alt. 전략 생성 (OpenAI multi-agent backend)
OPENAI_API_KEY=sk-... PYTHONPATH=src python scripts/generate_strategy.py \
    --goal "Order imbalance alpha" --backend openai

# 2. 전략 검토
PYTHONPATH=src python scripts/review_strategy.py \
    strategies/imbalance_momentum_v1.0.json

# 3. 단일 종목 백테스트
PYTHONPATH=src python scripts/backtest.py \
    --spec strategies/imbalance_momentum_v1.0.json \
    --symbol 005930 --start-date 20260313

# 4. Universe 백테스트 (전체 종목 × 기본 latency sweep)
PYTHONPATH=src python scripts/backtest_strategy_universe.py \
    --spec strategies/imbalance_momentum_v1.0.json \
    --data-dir /home/dgu/tick/open-trading-api/data/realtime/H0STASP0 \
    --start-date 20260313

# 5. 결과 요약
PYTHONPATH=src python scripts/summarize_universe_results.py \
    --results outputs/universe_backtest/imbalance_momentum/universe_results.csv
```

## Strategy Spec 형식

```json
{
  "name": "imbalance_momentum",
  "version": "1.0",
  "signal_rules": [
    {"feature": "order_imbalance", "operator": ">", "threshold": 0.3, "score_contribution": 0.5}
  ],
  "filters": [
    {"feature": "spread_bps", "operator": ">", "threshold": 30.0, "action": "block"}
  ],
  "position_rule": {"max_position": 500, "sizing_mode": "signal_proportional"},
  "exit_rules": [
    {"exit_type": "stop_loss", "threshold_bps": 15.0},
    {"exit_type": "take_profit", "threshold_bps": 25.0},
    {"exit_type": "time_exit", "timeout_ticks": 300}
  ]
}
```

## Universe 평가 프로토콜

- 한 종목 결과만으로 결론 내리지 않는다
- 모든 적용 가능 종목에 적용 후 기본 요약:
  - **Mean** net_pnl, sharpe
  - **Median** net_pnl, sharpe
  - **Std** (종목 간 분산)
  - **Win rate** (수익 종목 비율)
- Latency는 기본 실험 축: 0ms, 50ms, 100ms, 500ms, 1000ms

## Latency를 기본 변수로 포함하는 이유

실제 트레이딩에서 latency는 전략 성과에 결정적 영향을 미친다:
- 0ms (이론적 최적): 전략의 순수 알파 측정
- 50ms (co-location): 기관 투자자 환경
- 100ms (일반 기관): 현실적 기관 환경
- 500ms~1s (리테일): 개인 투자자 환경

latency에 따라 성과가 급격히 변하는 전략은 실전 배포에 부적합하다.
