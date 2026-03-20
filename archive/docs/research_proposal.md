# LLM Multi-Agent 전략 연구 — 연구 제안

---

## 연구 동기

### LLM의 한계와 가능성

LLM은 LOB 요약 데이터로부터 방향성 판단을 생성할 수 있지만,
직접 트레이딩 정책으로 사용할 수 없다:

| 제약 | 설명 |
|------|------|
| **Latency** | API 호출 수백 ms~수 초 → 미시구조 시그널 유효 시간 초과 |
| **Cost** | 의사결정 빈도에 비례하는 추론 비용 |
| **Position Sizing** | 재고·spread·impact 고려한 최적화 불가 |

### 해결: LLM = 전략 생성자, 백테스트 = 검증자

LLM이 매 틱마다 주문하는 대신:
1. LLM이 **전략 사양(Strategy Spec)**을 생성
2. Spec을 **실행 가능한 Strategy 객체**로 컴파일
3. 기존 **백테스트 인프라**로 검증
4. **다종목 × 다 latency**로 체계적 평가

---

## 연구 질문

1. LLM Multi-Agent 파이프라인이 단일 LLM보다 더 좋은 전략을 생성하는가?
2. 생성된 전략이 handcrafted 전략보다 다종목에서 일관된 성과를 보이는가?
3. Latency에 따른 전략 성과 변화가 실전 배포 판단 기준으로 유효한가?
4. 어떤 Agent 역할이 전략 품질에 가장 큰 기여를 하는가?

---

## Multi-Agent 파이프라인 설계

```
┌─────────────────────────────────────┐
│  Researcher Agent                    │
│  연구 목표 → 전략 아이디어 생성     │
│  출력: name, hypothesis, features    │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  Factor Designer Agent               │
│  아이디어 → signal_rules, filters    │
│  출력: 구조화된 규칙 리스트          │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  Risk / Execution Agent              │
│  규칙 + latency → position, exits   │
│  출력: position_rule, exit_rules     │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  Reviewer Agent                      │
│  완성된 Spec → 검증                 │
│  출력: pass/fail + issues           │
└─────────────────────────────────────┘
```

---

## 실험 프로토콜

### Baseline 정의

| Baseline | 전략 | 비고 |
|----------|------|------|
| Handcrafted | MicroAlphaStrategy | 기존 규칙 기반 |
| Single-Agent LLM | LLMAlphaStrategy | LLM 단독 틱별 판단 |
| Multi-Agent | CompiledStrategy | 본 연구의 핵심 |

### 평가 축

1. **종목 축**: 모든 적용 가능 종목
2. **Latency 축**: 0, 50, 100, 500, 1000 ms
3. **집계 메트릭**: mean, median, std, win_rate

### 통계적 유의성

- Harvey, Liu & Zhu (2016)의 t > 3.0 threshold 적용
- 다종목 결과의 bootstrap CI 사용
- 단일 종목 과적합 방지

---

## 기대 기여

1. LLM → 구조화된 전략 사양 생성 파이프라인
2. Multi-Agent 역할 분리의 전략 품질 기여도 분석
3. Latency 기반 전략 실전 배포 적합성 평가 프레임워크
4. Universe 평가 프로토콜을 통한 과적합 방지 방법론
