# 틱 데이터 전략 생성 및 검증 플랫폼

전략 사양(Strategy Spec)을 생성하고, 정적 검토 후 컴파일하여,
다종목/latency 조건에서 체계적으로 백테스트하는 연구 플랫폼.

---

## 핵심 설계 철학

1. **전략은 구조화된 JSON Spec으로 저장된다** — 자유 텍스트가 아닌 기계 소비 가능 형식
2. **Compiler가 Spec을 Strategy 객체로 변환한다** — 기존 백테스트 엔진과 연결
3. **모든 적용 가능 종목에 백테스트한다** — 단일 종목 결과로 결론 내지 않음
4. **Latency는 기본 실험 축이다** — 0ms, 50ms, 100ms, 500ms, 1000ms

---

## 프로젝트 구조

```
proj_rl_agent/
├── src/
│   ├── strategy_generation/   # 전략 생성 (template / OpenAI multi-agent)
│   │   ├── templates.py       # 5개 전략 템플릿 + 키워드 매칭
│   │   ├── generator.py       # StrategyGenerator (backend 선택 + fallback)
│   │   ├── pipeline.py        # MultiAgentPipeline (4-agent 오케스트레이션)
│   │   ├── agents.py          # Researcher/FactorDesigner/RiskDesigner/LLMReviewer
│   │   ├── agent_schemas.py   # Pydantic 스키마 (IdeaBrief, SignalDraft, RiskDraft 등)
│   │   ├── assembler.py       # Agent 출력 → StrategySpec 결정론적 변환
│   │   └── openai_client.py   # OpenAI API 클라이언트 (live/replay/mock)
│   │
│   ├── strategy_review/       # 정적 규칙 기반 전략 검토
│   │   └── reviewer.py        # StrategyReviewer (7개 검증 카테고리)
│   │
│   ├── strategy_specs/        # 전략 사양 스키마
│   │   └── schema.py          # StrategySpec, SignalRule, FilterRule, PositionRule, ExitRule
│   │
│   ├── strategy_compiler/     # Spec → Strategy 컴파일러
│   │   └── compiler.py        # StrategyCompiler, CompiledStrategy
│   │
│   ├── strategy_registry/     # 전략 저장·관리
│   │   └── registry.py        # StrategyRegistry (파일 기반)
│   │
│   ├── strategy/              # Strategy 인터페이스
│   │   └── base.py            # Strategy ABC
│   │
│   ├── layer0_data/           # 데이터 수집·정제·동기화·피처
│   ├── layer1_signal/         # 시그널 데이터 타입 (Signal dataclass)
│   ├── layer2_position/       # 포지션 타겟·리스크 관리
│   ├── layer3_order/          # 주문 타입·델타 계산
│   ├── layer4_execution/      # 슬라이싱·배치·타이밍
│   ├── layer5_simulator/      # 체결·수수료·충격·latency
│   ├── layer6_evaluator/      # PnL·리스크·실행 품질
│   └── layer7_validation/     # 백테스트 오케스트레이션
│
├── scripts/
│   ├── generate_strategy.py          # 전략 사양 생성
│   ├── review_strategy.py            # 전략 사양 검토
│   ├── backtest.py                   # 단일 종목 백테스트
│   ├── backtest_strategy_universe.py # Universe 백테스트
│   ├── summarize_universe_results.py # 결과 집계
│   ├── collect_data.py               # 데이터 수집
│   └── visualize.py                  # 시각화
│
├── strategies/                # 생성된 전략 사양 저장소
├── conf/                      # YAML 설정
├── tests/                     # pytest 테스트
└── docs/                      # 문서
```

---

## 전략 생성 → 검토 → 컴파일

### StrategyGenerator

`src/strategy_generation/` — 두 가지 backend를 병행 지원하는 전략 사양 생성기.

**Template backend** (기본, `--backend template`):
- `--goal` 키워드에서 관련 템플릿 자동 선택 (가장 적합한 1개 생성)
- 5개 내장 템플릿: imbalance_momentum, spread_mean_reversion, trade_flow_pressure, depth_divergence, micro_price_alpha

**OpenAI multi-agent backend** (`--backend openai`):
- 4-Agent 파이프라인: Researcher → FactorDesigner → RiskDesigner → LLMReviewer
- OpenAI Structured Outputs로 Pydantic 스키마 기반 응답 생성
- 결정론적 Assembler가 agent 출력을 StrategySpec으로 변환
- API 실패 시 자동으로 template backend fallback
- `--mode mock`으로 API 키 없이 agent fallback 테스트 가능

공통:
- Static reviewer는 양쪽 backend 모두 필수 hard gate
- 백테스트 코어(Layer 0~7)는 backend에 무관하게 동일
- 생성된 Spec은 `StrategyRegistry`에 저장, trace JSON도 별도 저장

### StrategyReviewer

`src/strategy_review/` — 정적 규칙 기반 검토기.

7개 검증 카테고리:
| 카테고리 | 검토 내용 |
|----------|----------|
| schema | StrategySpec.validate() 통과 여부 |
| signal | 규칙 존재, 과다(>10), 단방향만 존재 |
| filter | 과다(>5), 비현실적 threshold |
| risk | stop_loss/time_exit 부재, 비현실적 설정 |
| position | max_position/inventory_cap 유효성 |
| redundancy | 동일 규칙 중복 |
| feature | 미지원 피처 사용 |

### StrategyCompiler

`src/strategy_compiler/` — Spec → CompiledStrategy 변환.
- 20+ 내장 피처 (LOB, trade, feature pipeline)
- 7개 비교 연산자 (`>`, `<`, `>=`, `<=`, `==`, `cross_above`, `cross_below`)
- 5개 exit 타입 (stop_loss, take_profit, trailing_stop, time_exit, signal_reversal)

---

## Strategy Spec 형식

```json
{
  "name": "strategy_name",
  "version": "1.0",
  "description": "...",
  "signal_rules": [
    {"feature": "...", "operator": ">|<|>=|<=|==|cross_above|cross_below",
     "threshold": 0.0, "score_contribution": 0.0, "description": "..."}
  ],
  "filters": [
    {"feature": "...", "operator": "...", "threshold": 0.0,
     "action": "block|reduce", "description": "..."}
  ],
  "position_rule": {
    "max_position": 1000, "sizing_mode": "signal_proportional|fixed|kelly",
    "fixed_size": 100, "holding_period_ticks": 0, "inventory_cap": 1000
  },
  "exit_rules": [
    {"exit_type": "stop_loss|take_profit|trailing_stop|time_exit|signal_reversal",
     "threshold_bps": 0.0, "timeout_ticks": 0, "description": "..."}
  ],
  "metadata": {}
}
```

---

## Universe 평가 프로토콜

모든 적용 가능 종목에 적용 후:
- **Mean** net_pnl, sharpe_ratio
- **Median** net_pnl, sharpe_ratio
- **Std** (종목 간 분산)
- **Win rate** (수익 종목 비율)

### Latency 실험 축

| Latency | 프로필 | 대상 |
|---------|--------|------|
| 0ms | 이론적 최적 | 순수 알파 측정 |
| 50ms | Co-location | 기관 HFT |
| 100ms | 일반 기관 | 현실적 기관 |
| 500ms | 느린 기관 | API 기반 기관 |
| 1000ms | 리테일 | 개인 투자자 |

---

## 7계층 백테스팅 파이프라인

```
Layer 0: Data       — 수집, 정제, 동기화, 피처
Layer 1: Signal     — 시그널 인터페이스
Layer 2: Position   — 포지션 타겟, 리스크
Layer 3: Order      — 주문 타입, 델타
Layer 4: Execution  — 슬라이싱, 배치
Layer 5: Simulator  — 체결, 수수료, 충격, latency
Layer 6: Evaluator  — PnL, 리스크, 실행 품질
Layer 7: Validation — 백테스트 오케스트레이션
```

---

## Legacy / Archive

`archive/` 디렉토리에는 비활성 코드와 문서가 보관되어 있다.
이들은 런타임에서 참조되지 않으며, 히스토리 참고용이다.

| 경로 | 내용 |
|------|------|
| `archive/legacy_baselines/` | MicroAlphaStrategy, micro_alpha.py 등 |
| `archive/legacy_agents/` | llm_agents/ (LLM 기반 4-Agent 파이프라인) |
| `archive/docs/` | 과거 연구 제안서, 모델 명세, Agent 역할 명세 |
