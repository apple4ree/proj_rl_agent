# 설계 의사결정 기록 (ADR)

프로젝트의 주요 설계 결정과 그 배경을 기록합니다.

---

## ADR-015: RL → 전략 Spec 기반 연구 플랫폼 전환

**상태**: 채택됨 (historical — ADR-019에 의해 확장)

### 맥락

기존 프로젝트는 PPO 기반 RL 에이전트가 매 틱마다 행동을 결정하는 구조였다.
Strategy Spec 기반 전략 생성이 더 유연하고 해석 가능하며,
다양한 전략을 빠르게 탐색할 수 있는 장점이 있다.

### 결정

프로젝트의 연구 목적을 근본적으로 전환한다:

| 기존 | 신규 |
|------|------|
| RL이 매 틱마다 행동 결정 | 전략 사양을 먼저 생성 |
| 단일 에이전트 | 전략 생성 + 검토 + 컴파일 파이프라인 |
| 단일 종목 학습/평가 | Universe (전종목) 백테스트 |
| Latency 미고려 | Latency를 기본 실험 변인으로 포함 |

### 근거

- **해석 가능성**: Strategy Spec은 사람이 읽고 수정할 수 있는 JSON
- **빠른 탐색**: 학습 없이 전략 생성 → 즉시 백테스트
- **재현성**: 동일 Spec → 동일 백테스트 결과
- **인프라 재활용**: Layer 0~7 백테스팅 파이프라인을 그대로 사용

### 결과

- 메인 경로에서 RL 의존성 완전 제거 (`stable-baselines3` 불필요)
- 새 엔트리포인트: `generate_strategy.py`, `backtest_strategy_universe.py`
- 기존 `backtest.py`에 `--spec path.json` 옵션 추가

---

## ADR-016: Strategy Spec JSON 포맷

**상태**: 채택됨

### 맥락

LLM이 생성한 전략을 어떤 형식으로 저장할 것인가.

### 결정

JSON 기반 구조화된 스키마를 사용한다:
- `signal_rules`: feature + operator + threshold + score_contribution
- `filters`: 사전 거래 필터
- `position_rule`: 포지션 크기, 보유 기간, 인벤토리 캡
- `exit_rules`: 손절/익절/시간 제한

### 근거

- **기계 소비 가능**: 다음 Agent가 바로 파싱 가능
- **검증 가능**: JSON Schema로 유효성 검증
- **버전 관리**: 파일 기반 저장 → git 추적 가능
- **확장 가능**: 새 필드 추가 시 하위 호환 유지

---

## ADR-017: 4-Agent Multi-Agent 파이프라인

**상태**: superseded — ADR-019에 의해 대체. LLM Agent 코드는 `archive/legacy_agents/`로 이동됨. 현재는 템플릿 기반 생성 + 정적 규칙 기반 검토로 대체.

### 맥락

전략 생성을 단일 LLM 호출로 할 것인가, 역할 분리된 Multi-Agent로 할 것인가.

### 결정 (historical)

4개 역할로 분리: Researcher, Factor Designer, Risk/Execution, Reviewer.

### 대체 사유

LLM Agent 의존성(OpenAI API)이 오프라인 환경에서 실행 불가. 템플릿 기반 생성이 deterministic하고 재현 가능하며, 정적 검토가 LLM 검토보다 일관성 있음. 향후 LLM 기반 생성이 필요하면 `archive/legacy_agents/`에서 복원 가능.

---

## ADR-018: Universe 평가 프로토콜

**상태**: 채택됨

### 맥락

전략 성과를 어떻게 평가할 것인가.

### 결정

모든 적용 가능 종목에 백테스트 후, mean/median/std/win_rate로 집계한다.
Latency는 기본 실험 축으로 포함 (0, 50, 100, 500, 1000ms).

### 근거

- **과적합 방지**: 단일 종목 최적화는 일반화 불가
- **분산 추정**: std로 전략의 안정성 측정
- **실전 대비**: latency에 따른 성과 변화가 실전 배포 판단 기준

---

## ADR-001: 이중 LOBSnapshot 아키텍처

**상태**: 폐기됨 — ADR-015에 의해 대체. RL 환경(`src/data/`) 삭제로 `ArrayLOBSnapshot`이 제거되어, `LOBSnapshot` dataclass만 남음.

---

## ADR-002: 7계층 수직 아키텍처

**상태**: 채택됨

### 맥락

틱 단위 투자 시스템은 데이터 수집부터 성과 평가까지 많은 단계를 포함한다. 이를 어떻게 조직할 것인가.

### 결정

기능별 7개 레이어로 수직 분할한다:

```
Layer 0: Data       — 수집, 정제, 동기화, 피처
Layer 1: Signal     — 알파 시그널 생성, 신뢰도
Layer 2: Position   — 포지션 타겟, 리스크 관리
Layer 3: Order      — 주문 타입, 델타 계산
Layer 4: Execution  — 슬라이싱, 배치, 타이밍
Layer 5: Simulator  — 체결, 수수료, 충격
Layer 6: Evaluator  — PnL, 리스크, 실행 품질
Layer 7: Validation — 백테스트 오케스트레이션, 검증
```

### 근거

- **단방향 의존성**: 각 레이어는 하위 레이어에만 의존 → 순환 의존성 방지
- **독립 테스트**: 각 레이어를 mock으로 독립 테스트 가능
- **데이터 계약**: 레이어 간 통신은 명확한 데이터 타입 (`MarketState → Signal → TargetPosition → ParentOrder → FillEvent`)
- **점진적 구축**: MVP에서 Layer 1-2를 건너뛰고 외부 전략으로 대체 가능

### 대안 검토

| 대안 | 기각 사유 |
|------|----------|
| 모놀리식 단일 파일 | 유지보수 불가 |
| 수평 분할 (데이터 타입별) | 워크플로우 흐름 파악 어려움 |
| 이벤트 드리븐 아키텍처 | 백테스트에는 과도한 복잡성 |

### 결과

- 레이어 간 결합도 최소화
- `PipelineRunner`가 전체 흐름을 오케스트레이션
- 레이어 추가/교체가 용이 (예: Layer 4에 새 슬라이서 추가)

---

## ADR-003: Parent-Child 주문 계층구조

**상태**: 채택됨

### 맥락

대량 주문(예: 1,000주 매수)을 시장에 그대로 보내면 충격이 크다. 이를 어떻게 모델링할 것인가.

### 결정

2단계 주문 계층을 도입한다:

- **ParentOrder**: 전체 거래 의도 (종목, 방향, 총수량, 긴급도)
- **ChildOrder**: ParentOrder에서 파생된 개별 주문 (수량, 가격, 주문유형, TIF)

관계: `ParentOrder.child_orders[]` ↔ `ChildOrder.parent_id`

### 근거

- **알고리즘 트레이딩 표준**: 업계 표준 패턴 (대형 주문 슬라이싱)
- **실행 유연성**: 동일 ParentOrder에 대해 TWAP, VWAP, AC 등 다른 슬라이싱 적용 가능
- **체결 집계**: ChildOrder 체결을 ParentOrder로 롤업하여 전체 성과 측정
- **KRX 맥락**: 거래소에 제출하는 단위는 개별 주문 (ChildOrder)

### 대안 검토

| 대안 | 기각 사유 |
|------|----------|
| 단일 Order 타입 | 슬라이싱 추상화 불가, 실행 로직이 주문 생성에 침투 |
| Parent + SlicingSchedule 분리 | 추적이 어려움 |
| 트리 계층 (Parent → Sub-parent → Child) | MVP에 과도 |

### 결과

- FillSimulator가 Child/Parent 모두 업데이트하여 일관성 유지
- IS, VWAP 등 메트릭을 양쪽 레벨에서 계산 가능
- 7종 주문유형 (MARKET, LIMIT, LIMIT_IOC, LIMIT_FOK, PEG_MID, STOP, STOP_LIMIT)
- 5종 TIF (DAY, GTC, IOC, FOK, GTX)

---

## ADR-004: 4종 슬라이싱 전략 병렬 지원

**상태**: 채택됨 (ADR-015에 의해 RL 슬라이서 제거, 5종→4종)

### 맥락

주문 분할 방식에 따라 실행 품질이 크게 달라진다. 어떤 전략을 지원할 것인가.

### 결정

4종 슬라이서를 플러그인 방식으로 지원한다:

| 전략 | 스케줄 방식 | 사용 시점 |
|------|-----------|---------|
| **TWAP** | 시간 균등 | 유동성·변동성 안정 시 |
| **VWAP** | 거래량 비례 | 일중 거래량 패턴 예측 가능 시 |
| **POV** | 실시간 거래량 참여율 | 동적 적응 필요 시 |
| **Almgren-Chriss** | 비용-리스크 최적화 | 충격 파라미터 알려진 경우 |

공통 인터페이스: `generate_schedule(parent, states) → list[(qty, step)]`

### 근거

- **벤치마크 비교**: TWAP/VWAP 베이스라인 vs AC 최적 → 성능 비교 가능
- **시장 상황별 적합성**: 단일 전략으로 모든 상황 대응 불가
- **설정 기반 전환**: 코드 변경 없이 config에서 슬라이서 선택
- **학술적 가치**: AC는 이론적 최적 → 비교 연구

### 대안 검토

| 대안 | 기각 사유 |
|------|----------|
| TWAP만 구현 | 벤치마크 비교 불가 |
| 범용 하이브리드 슬라이서 | 복잡도 증가, 디버깅 어려움 |
| 슬라이서 선택을 OrderGenerator 내부에 | 테스트 어려움, 관심사 혼합 |

### 결과

- POV만 `on_fill()` 콜백 필요 (동적 적응)
- AC 슬라이서는 η, γ, σ 캘리브레이션 필요 (파라미터 리스크)
- 4 슬라이서 × 3 배치정책 = 12가지 조합 → 테스트 부담

---

## ADR-005: KRX 전용 수수료 모델

**상태**: 채택됨

### 맥락

백테스트의 비용 현실성을 위해 수수료 모델이 필요하다. 어떤 시장을 대상으로 할 것인가.

### 결정

KRX(한국거래소) 전용 수수료 모델을 구현한다:

- 위탁수수료: BUY/SELL 양방향 (기본 1.5 bps)
- 증권거래세: SELL 단방향 (KOSPI 18 bps, KOSDAQ 20 bps)

### 근거

- **규제 현실성**: 한국 시장의 비대칭 수수료 구조 (매도 시 거래세 부과)는 실행 전략에 직접 영향
- **비용 비대칭**: SELL이 BUY보다 ~12-13배 비싸므로 (1.5 vs 19.5 bps), 이를 무시하면 백테스트 왜곡
- **시장별 차이**: KOSPI vs KOSDAQ 세율 차이도 전략에 영향
- **테스트 분리**: ZeroFeeModel로 수수료 영향 제외한 순수 충격 연구 가능

### 대안 검토

| 대안 | 기각 사유 |
|------|----------|
| 균일 수수료 | KRX 규제 현실 미반영 |
| 대칭 수수료 | BUY/SELL 비대칭 무시 |
| 미국 시장 모델 (maker/taker) | 대상 시장 불일치 |

### 결과

- SELL 주문이 BUY보다 비싸므로 포지션 진입/청산 비대칭 발생
- AC 슬라이서가 세금 지연 효과를 직접 모델링하지는 않음 (향후 개선 여지)
- API에 `is_maker` 파라미터 포함하여 향후 maker 리베이트 도입 시 확장 가능

---

## ADR-006: 이산 행동 공간 (11 bins)

**상태**: 폐기됨 — ADR-015에 의해 대체. RL 에이전트 제거로 행동 공간 설계가 더 이상 해당 없음.

---

## ADR-007: PipelineRunner 분해 (FillSimulator + ReportBuilder)

**상태**: 채택됨 (리팩토링)

### 맥락

PipelineRunner가 1,103줄의 모놀리스로 성장했다. 체결 시뮬레이션, 리포트 생성, 오케스트레이션이 모두 한 파일에 혼재.

### 결정

3개 모듈로 분해한다:

| 모듈 | 역할 | 줄 수 |
|------|------|-------|
| `PipelineRunner` | 오케스트레이션만 | ~450 |
| `FillSimulator` | 체결, 충격, 수수료, 기록 | ~200 |
| `ReportBuilder` | Layer 6 리포트 생성·저장 | ~200 |

추가로 `BacktestConfig`, `BacktestResult` 데이터 클래스를 `backtest_config.py`로 추출.

### 근거

- **단일 책임 원칙**: 오케스트레이터는 조율만, 시뮬레이션/리포팅은 전문 클래스에 위임
- **테스트 용이성**: FillSimulator를 mock MatchingEngine으로 독립 테스트 가능
- **재사용**: FillSimulator를 PipelineRunner 외부에서도 사용 가능
- **인지 부하**: 200줄 × 3 ≫ 1,100줄 × 1 (읽기 쉬움)

### 대안 검토

| 대안 | 기각 사유 |
|------|----------|
| 그대로 유지 | 유지보수 어려움, 테스트 어려움 |
| Mixin 사용 | 순환 의존성, mock 어려움 |
| 마이크로서비스 | 백테스트에 과도 |

### 결과

- PipelineRunner가 FillSimulator, ReportBuilder를 의존성 주입으로 생성
- 하위 호환 래퍼 유지: `_simulate_fills()`, `_record_fills()`, `save_results()`
- `__init__.py`에서 새 클래스 모두 export

---

## ADR-008: 4종 보상 함수와 팩토리 패턴

**상태**: 폐기됨 — ADR-015에 의해 대체. RL 보상 함수(`src/env/`) 삭제로 더 이상 해당 없음.

---

## ADR-009: 워크포워드 교차검증 (embargo + purge)

**상태**: historical — 구현 코드(`walk_forward.py`)가 삭제됨. 개념은 유효하나 현재 코드에 적용되어 있지 않음.

### 맥락

시계열 데이터에서 일반적인 k-fold 교차검증은 미래 정보 누수를 유발합니다. 이를 어떻게 검증할 것인가.

### 결정

워크포워드 분할에 embargo(갭)와 purge(제거)를 적용합니다:

```
|← train (100) →| purge(3) | embargo(5) |← val (20) →|← test (20) →|
   학습 구간       라벨 겹침    자기상관 차단   검증 구간      OOS 테스트
                   제거         갭
```

### 근거

- **시간 순서 존중**: 과거로만 학습, 미래로만 검증 (look-ahead 방지)
- **Embargo**: 자기상관된 피처가 train→val로 누수되는 것을 갭으로 차단
- **Purge**: 라벨이 미래 수익률을 포함할 때 train 마지막 N개 샘플을 제거하여 라벨 겹침 방지
- **다중 폴드**: 단일 OOS 기간보다 분산이 낮은 성능 추정

### 대안 검토

| 대안 | 기각 사유 |
|------|----------|
| 랜덤 k-fold | 시간 순서 위반, look-ahead |
| 단순 80/20 분할 | 높은 분산, 단일 OOS 기간 |
| embargo 없는 blocked CV | 자기상관 누수 |
| anchored expanding window | 학습 세트 다양성 부족 |

### 결과

- 최소 데이터 필요: `train + purge + embargo + val + test` 이상
- Purge로 학습 데이터 감소 → 누수 방지와 데이터 효율의 트레이드오프
- 각 폴드별 독립 재학습 필요 (비용 증가)

---

## ADR-010: 미래 정보 누수 전용 검사 레이어

**상태**: historical — 구현 코드(`leakage_check.py`)가 삭제됨. 개념은 유효하나 현재 코드에 적용되어 있지 않음.

### 맥락

백테스트에서 look-ahead bias는 결과를 무효화하는 치명적 오류입니다. 이를 어떻게 방지할 것인가.

### 결정

`LeakageChecker`를 전용 클래스로 구현하여 6종 검사를 제공한다:

| 검사 | 감지 대상 |
|------|----------|
| feature_label_timestamps | 피처 타임스탬프 ≥ 라벨 타임스탬프 |
| survivorship | 백테스트 시작일에 존재하지 않던 종목 |
| forward_fill_leakage | bfill로 미래 값이 과거로 전파 |
| index_alignment | 피처/라벨 최대 타임스탬프 불일치 |
| timestamp_monotonic | 시간 역전 또는 중복 |
| check_all | 위 5종 통합 실행 |

### 근거

- **치명적 위험**: 1 bps의 미래 정보 누수도 백테스트를 무의미하게 만듦
- **일반적 실수 패턴**: bfill, 미래 수익률 피처, 타임스탬프 불일치는 흔한 실수
- **명시적 > 암묵적**: 전용 레이어로 만들어야 "검사를 건너뛰는" 실수 방지
- **디버깅 지원**: 위반 유형 + 심각도 + 영향 행 수를 보고하여 문제 추적 용이

### 대안 검토

| 대안 | 기각 사유 |
|------|----------|
| 검사 없음 | 위험 |
| PipelineRunner 내부에 내장 | 관심사 혼합, 선택적 건너뛰기 어려움 |
| 단일 catch-all 검사 | 세분화된 진단 불가 |

### 결과

- 위반은 경고(warning)이며 강제 중단 아님 → 사용자가 확인 후 진행 가능
- 일부 휴리스틱 검사 (bfill 패턴)에서 false positive 가능
- 수동 호출 필요 (파이프라인에 자동 통합되지 않음)

---

## ADR-011: 합성 LOB 생성기 (SyntheticLOBGenerator)

**상태**: 폐기됨 — ADR-015에 의해 대체. `src/data/` 삭제로 합성 LOB 생성기가 제거됨. 현재는 실제 KIS H0STASP0 데이터를 사용.

---

## ADR-012: 다중 대기열 모델 (Queue Models)

**상태**: 채택됨

### 맥락

지정가 주문이 호가창에 대기할 때, 실제 대기 위치를 알 수 없다. 이를 어떻게 시뮬레이션할 것인가.

### 결정

5종 대기열 모델을 제공하여 민감도 분석을 가능하게 한다:

| 모델 | 대기열 비율 | 특성 |
|------|-----------|------|
| PRICE_TIME | q (선형) | 표준 FIFO |
| RISK_ADVERSE | q (선형) | 보수적 |
| PROB_QUEUE | q² (이차) | 낙관적 |
| PRO_RATA | Q/(V+Q) | 비례 배분 |
| RANDOM | Uniform | 균일 랜덤 |

### 근거

- **불확실성 모델링**: 실제 대기 위치는 관측 불가 → 확률적 접근 필요
- **민감도 분석**: 대기열 가정에 따른 체결률 변화를 비교 → 전략 강건성 확인
- **거래소별 차이**: KRX, 미국, 암호화폐 거래소의 매칭 방식이 상이
- **hftbacktest 참고**: 검증된 백테스팅 프레임워크의 개념 차용

### 대안 검토

| 대안 | 기각 사유 |
|------|----------|
| 고정 50% 대기 위치 | 너무 단순 |
| 항상 최우선/최후선 | 극단적, 비현실적 |
| ML 기반 대기열 모델 | 미시구조 데이터로 캘리브레이션 필요 |

### 결과

- PROB_QUEUE (기본값)가 적당히 낙관적이면서 현실적
- PRO_RATA는 queue_position_assumption을 사용하지 않음 (주문 독립적)
- 대기열 모델 선택이 체결률에 큰 영향 → 5종 모두 테스트 권장
- 설정에서 선택; 나머지 코드 변경 불필요

---

## ADR-013: 규칙 기반 베이스라인과 RL 에이전트 병행

**상태**: 폐기됨 — ADR-015에 의해 대체. RL 에이전트(`src/agent/`) 삭제로 더 이상 해당 없음. 전략 비교는 Universe 평가 프로토콜(ADR-018)로 대체.

---

## ADR-014: 42차원 관측 공간 설계

**상태**: 폐기됨 — ADR-015에 의해 대체. RL 관측 공간(`to_obs_array()`) 삭제로 더 이상 해당 없음.

---

## ADR-019: 템플릿 기반 전략 생성 + 정적 규칙 기반 검토

**상태**: 채택됨

### 맥락

ADR-017에서 채택한 LLM 4-Agent 파이프라인은 OpenAI API 의존성으로 인해 오프라인 환경에서 실행 불가했다. Agent 코드가 `archive/legacy_agents/`로 이동된 후, `generate_strategy.py`와 `review_strategy.py`가 실행 불가 상태였다.

### 결정

LLM Agent 의존성을 완전히 제거하고, 다음으로 대체한다:

| 구성요소 | 이전 (ADR-017) | 현재 |
|---------|---------------|------|
| 전략 생성 | 4개 LLM Agent 파이프라인 | `StrategyGenerator` — 템플릿 기반 + 키워드 매칭 |
| 전략 검토 | LLM `ReviewerAgent` | `StrategyReviewer` — 정적 규칙 7개 카테고리 |

### 새 모듈

- `src/strategy_generation/` — StrategyGenerator, IDEA_TEMPLATES (5개 내장 템플릿)
- `src/strategy_review/` — StrategyReviewer, ReviewResult (7개 검증 카테고리)

### 근거

- **Deterministic**: 동일 입력 → 동일 출력 (재현성 보장)
- **오프라인 실행**: 외부 API 의존성 없음
- **즉시 실행**: API 호출 지연 없이 밀리초 단위 생성
- **확장 가능**: 새 템플릿/검토 규칙 추가가 코드 변경만으로 가능
- **일관된 검토**: 정적 규칙은 LLM보다 일관성 있고 예측 가능

### 결과

- `generate_strategy.py` — `from strategy_generation import StrategyGenerator`
- `review_strategy.py` — `from strategy_review import StrategyReviewer`
- `archive/legacy_agents/` — LLM Agent 코드 보관 (향후 복원 가능)
- 기존 CLI 인터페이스 (`--goal`, `--all`, `--latency-ms` 등) 유지
- LLM 전용 옵션 (`--llm-mode`, `--openai-model`, `--temperature`) 제거
