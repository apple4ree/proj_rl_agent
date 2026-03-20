# Multi-Agent 역할 명세

> **Archived**: `src/llm_agents/` 디렉토리는 `archive/legacy_agents/`로 이동됨.
> 아래 문서는 아카이브된 Agent 설계의 참고 자료로 유지합니다.

---

## 개요

4개 LLM Agent가 전략 생성 파이프라인을 구성합니다.
각 Agent는 구조화된 입력을 받아 구조화된 출력을 생성합니다.

모든 Agent는 두 가지 모드를 지원합니다:
- **Live**: LLM API 호출 (OpenAI 등)
- **Mock/Heuristic**: 내장 규칙 기반 (API 키 불필요)

---

## 1. Researcher Agent

**위치**: `archive/legacy_agents/researcher.py`

**역할**: 연구 목표와 시장 컨텍스트로부터 전략 아이디어를 생성

**입력**:
- `research_goal` (str): 연구 목표
- `market_context` (dict): 시장 정보 (종목, 날짜 등)
- `n_ideas` (int): 생성할 아이디어 수

**출력**:
- `ideas` (list): 각 아이디어는 다음을 포함
  - `name`: 전략 이름
  - `hypothesis`: 시장 비효율성 가설
  - `rationale`: 틱 레벨에서 작동하는 이유
  - `suggested_features`: 사용할 피처 리스트
  - `expected_direction`: 시그널 → 매수/매도 매핑
  - `risk_notes`: 알려진 리스크

**Heuristic 내장 전략**:
1. `imbalance_momentum` — 호가잔량 불균형 모멘텀
2. `spread_mean_reversion` — 스프레드 평균 회귀
3. `trade_flow_pressure` — 체결 흐름 압력

---

## 2. Factor Designer Agent

**위치**: `archive/legacy_agents/factor_designer.py`

**역할**: 전략 아이디어를 구체적인 signal_rules와 filters로 변환

**입력**:
- `idea` (dict): Researcher의 아이디어

**출력**:
- `signal_rules` (list): 각 규칙은 {feature, operator, threshold, score_contribution, description}
- `filters` (list): 각 필터는 {feature, operator, threshold, action, description}

**사용 가능 피처**:
`order_imbalance`, `depth_imbalance`, `spread_bps`, `trade_flow_imbalance`,
`bid_depth_5`, `ask_depth_5`, `volume_surprise`, `micro_price`

---

## 3. Risk / Execution Agent

**위치**: `archive/legacy_agents/risk_agent.py`

**역할**: 포지션 규칙, 손절/익절, latency 고려 규칙 추가

**입력**:
- `idea` (dict): 원본 아이디어
- `signal_rules` (list): Factor Designer 출력
- `filters` (list): Factor Designer 출력
- `latency_ms` (float): 예상 실행 latency

**출력**:
- `position_rule` (dict): {max_position, sizing_mode, fixed_size, holding_period_ticks, inventory_cap}
- `exit_rules` (list): {exit_type, threshold_bps, timeout_ticks, description}
- `additional_filters` (list): 추가 리스크 필터

**Latency 적응**:
- latency > 100ms → holding_period 증가
- latency > 50ms → 추가 spread 필터

---

## 4. Reviewer Agent

**위치**: `archive/legacy_agents/reviewer.py`

**역할**: 완성된 StrategySpec의 품질 검증

**입력**:
- `spec` (dict): 완성된 StrategySpec

**출력**:
- `passed` (bool): 에러 없으면 true
- `issues` (list): 각 이슈는 {category, severity, description, suggestion}
- `modifications` (dict | None): 제안된 수정 사항

**검증 카테고리**:
| 카테고리 | 설명 |
|----------|------|
| `look_ahead_bias` | 미래 정보 사용 위험 |
| `excessive_complexity` | 규칙 과다 (과적합 위험) |
| `non_executable_rules` | 사용 불가 피처 참조 |
| `redundant_rules` | 중복/모순 규칙 |
| `unrealistic_parameters` | 비현실적 파라미터 |
| `missing_risk_controls` | 리스크 관리 부재 |
