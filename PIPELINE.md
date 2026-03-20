# 파이프라인 — 전략 생성 → 검토 → 컴파일 → 백테스트 → 평가

```
┌──────────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌──────────────┐
│  1. 전략 생성     │──▶│  2. 전략 검토  │──▶│  3. 컴파일    │──▶│  4. 백테스트      │──▶│  5. 평가·요약  │
│ strategy_generation│  │ strategy_review│  │ strategy_compiler│ │ Layer 0~7       │  │ summarize    │
└──────────────────┘   └──────────────┘   └──────────────┘   └──────────────────┘   └──────────────┘
```

---

## 1단계: 전략 생성

**스크립트**: `scripts/generate_strategy.py`
**모듈**: `src/strategy_generation/`

현재 template backend와 OpenAI multi-agent backend를 병행 지원한다.
백테스트 코어(Layer 0~7)는 backend에 무관하게 동일하며, static reviewer는 양쪽 모두 필수이다.

### Backend A: Template (기본)

```
--goal "Order imbalance alpha"
  ↓  키워드 매칭 (select_ideas_for_goal)
IDEA_TEMPLATES에서 관련 템플릿 선택
  ↓  StrategyGenerator._build_spec()
  ↓  latency 보정 (holding_period, time_exit)
StrategySpec 생성
  ↓  StrategyRegistry.save()
strategies/{name}_v{version}.json 저장
```

내장 템플릿 (5개):
| # | 이름 | 핵심 feature |
|---|------|-------------|
| 0 | imbalance_momentum | order_imbalance, depth_imbalance |
| 1 | spread_mean_reversion | spread_bps, order_imbalance (contrarian) |
| 2 | trade_flow_pressure | trade_flow_imbalance |
| 3 | depth_divergence | depth_imbalance + trade_flow (contrarian) |
| 4 | micro_price_alpha | order_imbalance, bid/ask_depth_5 |

### Backend B: OpenAI Multi-Agent (`--backend openai`)

```
--goal "Order imbalance alpha" --backend openai
  ↓  ResearcherAgent: goal → IdeaBriefList (n개 아이디어)
  ↓  FactorDesignerAgent: idea → SignalDraft (signal rules + filters)
  ↓  RiskDesignerAgent: idea + signal → RiskDraft (position + exit rules)
  ↓  Assembler: agent 출력 → StrategySpec (결정론적 변환)
  ↓  LLMReviewerAgent: soft critique (재설계 루프)
  ↓  Static Reviewer: hard gate (필수)
StrategySpec 생성
```

4-Agent 구조:
| Agent | 입력 | 출력 | 역할 |
|-------|------|------|------|
| ResearcherAgent | goal (str) | IdeaBriefList | 리서치 아이디어 생성 |
| FactorDesignerAgent | IdeaBrief | SignalDraft | 시그널/필터 규칙 설계 |
| RiskDesignerAgent | IdeaBrief + SignalDraft | RiskDraft | 포지션/exit 규칙 설계 |
| LLMReviewerAgent | StrategySpec dict | ReviewDecision | 소프트 리뷰 |

Fallback 정책: OpenAI API 실패 시 자동으로 template backend로 전환.
`--mode mock`으로 API 키 없이 agent fallback 로직 테스트 가능.

---

## 2단계: 전략 검토

**스크립트**: `scripts/review_strategy.py`
**모듈**: `src/strategy_review/`

```
strategies/{name}_v{version}.json
  ↓  StrategySpec.load()
StrategySpec
  ↓  StrategyReviewer.review()
ReviewResult (passed/failed + issues)
```

검토 규칙 (7개 카테고리):
- **schema**: 필수 필드, 유효 연산자/액션/exit 타입
- **signal**: 규칙 존재 여부, 과다(>10), 단방향만 존재
- **filter**: 과다(>5), 비현실적 threshold
- **risk**: stop_loss/time_exit 부재, 비현실적 설정
- **position**: max_position/inventory_cap 유효성
- **redundancy**: 동일 규칙 중복
- **feature**: 미지원 피처 사용

---

## 3단계: 컴파일 + 데이터 준비

**모듈**: `src/strategy_compiler/`, `src/layer0_data/`

```
StrategySpec
  ↓  StrategyCompiler.compile()
CompiledStrategy (Strategy ABC 구현체)

KIS H0STASP0 CSV
  ↓  DataIngester → DataCleaner → FeaturePipeline → MarketStateBuilder
MarketState[] (LOB 스냅샷 + 피처 + 메타데이터)
```

---

## 4단계: 백테스트

### 단일 종목

**스크립트**: `scripts/backtest.py`

```
CompiledStrategy + MarketState[]
  ↓  PipelineRunner.run()
MarketState → Strategy.generate_signal() → Signal
  ↓  TargetBuilder → DeltaComputer → ParentOrder
  ↓  SlicingPolicy → PlacementPolicy → ChildOrder
  ↓  MatchingEngine → FillEvent
  ↓  Bookkeeper → PnLLedger → Reports
BacktestResult (summary JSON + artifacts)
```

### Universe (다종목 × 다 latency)

**스크립트**: `scripts/backtest_strategy_universe.py`

```
전체 종목 발견 (DataIngester.list_symbols)
  ↓
종목별 × latency별 backtest (순차 실행)
  ↓
universe_results.csv 집계
```

내부 기본값: 전체 종목, latency sweep [0,50,100,500,1000]ms.

---

## 5단계: 평가 및 요약

**스크립트**: `scripts/summarize_universe_results.py`

```
universe_results.csv
  ↓  group by latency_ms (기본)
집계 메트릭:
  mean, median, std, min, max, win_rate
  → net_pnl, sharpe_ratio, max_drawdown, fill_rate
```

---

## 핵심 데이터 타입 — 단계별 입출력

```
MarketState ──▶ Signal ──▶ TargetPosition ──▶ ParentOrder ──▶ ChildOrder ──▶ FillEvent ──▶ Reports
  (LOB+피처)   (예측+신뢰도) (종목→목표수량)   (대량주문)     (개별주문)     (체결기록)    (평가결과)
```

---

## 스크립트 요약

| 스크립트 | 단계 | 용도 |
|---------|------|------|
| `generate_strategy.py` | 1 (생성) | 전략 사양 생성 (template / OpenAI multi-agent) |
| `review_strategy.py` | 2 (검토) | 정적 규칙 기반 사양 검토 |
| `backtest.py` | 3~4 (백테스트) | 단일 종목 백테스트 |
| `backtest_strategy_universe.py` | 3~4 (백테스트) | 다종목 × 다 latency 백테스트 |
| `summarize_universe_results.py` | 5 (평가) | Universe 결과 집계 |
| `collect_data.py` | 데이터 | 시장 데이터 수집 |
| `visualize.py` | 시각화 | 결과 시각화 |

---

## Layer 0~7 상세

### Layer 0: Data

| 모듈 | 핵심 클래스 | 역할 |
|------|-----------|------|
| `ingestion.py` | `DataIngester` | KIS CSV에서 틱 데이터 로드 |
| `cleaning.py` | `DataCleaner` | 비정상 틱 감지·제거 |
| `synchronization.py` | `DataSynchronizer` | 다종목 시간 정렬 |
| `feature_pipeline.py` | `MicrostructureFeatures` | 스프레드, 불균형, 깊이, 충격 등 피처 |
| `market_state.py` | `MarketState`, `LOBSnapshot` | 시장 상태 데이터 계약 |
| `state_builder.py` | `MarketStateBuilder` | 수집→정제→피처→상태 오케스트레이션 |

### Layer 1: Signal

| 모듈 | 핵심 클래스 | 역할 |
|------|-----------|------|
| `signal.py` | `Signal` | 시그널 데이터 계약 (score, confidence, expected_return) |

### Layer 2: Position

| 모듈 | 핵심 클래스 | 역할 |
|------|-----------|------|
| `target_builder.py` | `TargetBuilder`, `TargetPosition` | 시그널 → 목표 포지션 |
| `risk_caps.py` | `RiskCaps` | 총노출/순노출/레버리지/집중도 제한 |
| `turnover_budget.py` | `TurnoverBudget` | 거래비용 예산 관리 |

### Layer 3: Order

| 모듈 | 핵심 클래스 | 역할 |
|------|-----------|------|
| `order_types.py` | `ParentOrder`, `ChildOrder` | 주문 데이터 타입 |
| `delta_compute.py` | `DeltaComputer` | 목표 vs 현재 → 델타 |
| `order_constraints.py` | `OrderConstraints` | 주문 크기/가격 범위 검증 |
| `order_scheduler.py` | `OrderScheduler` | 주문 제출 시점 스케줄링 |

### Layer 4: Execution

| 모듈 | 핵심 클래스 | 역할 |
|------|-----------|------|
| `slicing_policy.py` | TWAP, VWAP, POV, Almgren-Chriss | 대량 주문 분할 |
| `placement_policy.py` | Aggressive, Passive, SpreadAdaptive | 주문 가격·유형 결정 |
| `cancel_replace.py` | `CancelReplace` | 미체결 주문 취소·재배치 |
| `safety_guardrails.py` | `SafetyGuardrails` | 최대 금액/레버리지 사전 검증 |

### Layer 5: Simulator

| 모듈 | 핵심 클래스 | 역할 |
|------|-----------|------|
| `matching_engine.py` | `MatchingEngine` | LOB 기반 체결 시뮬레이션 |
| `impact_model.py` | `LinearImpact`, `SquareRootImpact` | 시장충격 모델링 |
| `fee_model.py` | `KRXFeeModel` | KRX 수수료·세금 |
| `latency_model.py` | `LatencyModel` | 주문 지연 시뮬레이션 |
| `bookkeeper.py` | `Bookkeeper`, `FillEvent` | 체결 기록·계좌 상태 |

### Layer 6: Evaluator

| 모듈 | 핵심 클래스 | 역할 |
|------|-----------|------|
| `pnl_ledger.py` | `PnLLedger`, `PnLReport` | 손익 추적 및 비용 분해 |
| `risk_metrics.py` | `RiskReport` | Sharpe, MDD, VaR 등 |
| `execution_metrics.py` | `ExecutionReport` | IS, VWAP 벤치마크 대비 |
| `attribution.py` | `AttributionReport` | 성과 귀인 분석 |

### Layer 7: Validation

| 모듈 | 핵심 클래스 | 역할 |
|------|-----------|------|
| `pipeline_runner.py` | `PipelineRunner` | 전체 백테스트 오케스트레이션 |
| `backtest_config.py` | `BacktestConfig`, `BacktestResult` | 백테스트 설정 및 결과 |
| `fill_simulator.py` | `FillSimulator` | 체결 시뮬레이션 위임 |
| `report_builder.py` | `ReportBuilder` | 리포트 생성 위임 |
| `reproducibility.py` | `ReproducibilityManager` | 실험 재현성 보장 |
