# 수학적 모델 명세

이 문서는 프로젝트에서 사용하는 모든 수학적 모델의 **수식, 파라미터, 단위, 특수 케이스**를 정리합니다.

> 이 프로젝트는 LLM Multi-Agent 전략 연구 플랫폼입니다. 핵심 모델은 섹션 1(충격), 2(수수료),
> 4(Almgren-Chriss), 5(마이크로 알파), 그리고 섹션 15(Strategy Spec 컴파일러)입니다.

---

## 단위 규약

| 단위 | 의미 | 예시 |
|------|------|------|
| **bps** | 1 베이시스 포인트 = 0.01% = 1/10,000 | 1.5 bps = 0.015% |
| **KRW** | 한국 원화 (절대 금액) | 수수료, PnL |
| **fraction** | 0~1 비율값 | 변동성 0.01 = 1% |
| **shares** | 주식 수량 (정수) | qty = 100 |
| **ms** | 밀리초 | 레이턴시 0.5ms |

**부호 규약:**
- IS 양수 = 불리한 체결 (매수 시 비싸게, 매도 시 싸게)
- Impact 양수 = 체결 가격 불리하게 이동
- Reward 음수 = 비용 발생

---

## 1. 시장충격 모델

### 1.1 선형 충격

> `src/layer5_simulator/impact_model.py` — `LinearImpact`

$$\text{temporary\_impact} = \eta \cdot \frac{Q}{ADV} \times 10{,}000 \quad [\text{bps}]$$

$$\text{permanent\_impact} = \gamma \cdot \frac{Q}{ADV} \times 10{,}000 \quad [\text{bps}]$$

$$\text{price\_delta} = \text{mid} \times \frac{\text{impact\_bps}}{10{,}000}$$

| 파라미터 | 기본값 | 의미 |
|---------|-------|------|
| η (eta) | 0.1 | 일시적 충격 계수 |
| γ (gamma) | 0.01 | 영구적 충격 계수 |

- 가격 조정: BUY → 가격 상승, SELL → 가격 하락
- ADV ≤ 0이면 0.0 반환

### 1.2 제곱근 충격

> `src/layer5_simulator/impact_model.py` — `SquareRootImpact`

$$\text{temporary\_impact} = \sigma \cdot \kappa \cdot \sqrt{\frac{Q}{ADV}} \times 10{,}000 \quad [\text{bps}]$$

$$\text{permanent\_impact} = \sigma \cdot \gamma \cdot \frac{Q}{ADV} \times 10{,}000 \quad [\text{bps}]$$

| 파라미터 | 기본값 | 의미 |
|---------|-------|------|
| σ (sigma) | 0.01 | 변동성 (fraction) |
| κ (kappa) | 0.1 | 일시적 충격 계수 |
| γ (gamma) | 0.01 | 영구적 충격 계수 |

- 4배 수량 → 2배 충격 (비선형 스케일링)
- ADV ≤ 0 또는 Q ≤ 0이면 0.0 반환

### 1.3 스프레드 비용 모델

> `src/layer5_simulator/impact_model.py` — `SpreadCostModel`

| 주문 유형 | 스프레드 비용 |
|----------|-------------|
| 시장가 (crossing) | 전체 스프레드 |
| 지정가 (book 안) | `spread_bps × fraction` |
| Maker (resting) | 0.0 |

지정가 주문의 fraction 계산 (BUY 기준):

$$\text{fraction} = \frac{\text{price} - \text{best\_bid}}{\text{best\_ask} - \text{best\_bid}}$$

---

## 2. 수수료 모델

### 2.1 KRX 수수료 모델

> `src/layer5_simulator/fee_model.py` — `KRXFeeModel`

$$\text{commission} = \text{notional} \times \frac{\text{commission\_bps}}{10{,}000}$$

$$\text{tax} = \text{notional} \times \frac{\text{tax\_bps}}{10{,}000} \quad (\text{SELL만 부과})$$

$$\text{total\_fee} = \text{commission} + \text{tax}$$

| 파라미터 | 기본값 | 의미 |
|---------|-------|------|
| commission_bps | 1.5 | 위탁수수료 (양방향) |
| KOSPI tax_bps | 18.0 | 증권거래세 0.18% |
| KOSDAQ tax_bps | 20.0 | 증권거래세 0.20% |

- **BUY**: 수수료만 부과 → `total_buy_bps = commission_bps`
- **SELL**: 수수료 + 거래세 → `total_sell_bps = commission_bps + tax_bps`
- notional = 0이면 0.0 반환

bps 변환:

$$\text{fee\_bps} = \frac{\text{total\_fee}}{\text{notional}} \times 10{,}000$$

---

---

## 4. 최적 집행 모델 (Almgren-Chriss)

### 4.1 최적 보유량 궤적

> `src/layer4_execution/slicing_policy.py` — `AlmgrenChrissSlicer`

$$x_j = X \cdot \frac{\sinh\bigl(\kappa \cdot (T - j\tau)\bigr)}{\sinh(\kappa \cdot T)}$$

여기서:

$$\kappa = \sqrt{\frac{\gamma}{\eta \cdot \tau}}, \quad \tau = \frac{T}{N}$$

| 기호 | 의미 | 기본값 |
|------|------|-------|
| X | 총 집행 수량 | — |
| T | 총 집행 기간 | 100 |
| N | 분할 수 | len(states) |
| η (eta) | 일시적 충격 계수 | 0.1 |
| γ (gamma) | 영구적 충격 계수 | 0.01 |
| σ (sigma) | 변동성 | 0.01 |

### 4.2 각 스텝 집행 수량

$$\Delta x_j = x_j - x_{j+1}$$

- 정수 변환: `floor(raw_qty)` 후 잔여분을 소수부가 큰 순서로 분배
- **특성**: γ > 0일 때 전반부 집중 (front-loaded) — 리스크 조기 해소

### 4.3 특수 케이스

| 조건 | 동작 |
|------|------|
| N ≤ 0 | 빈 배열 반환 |
| N = 1 | 전체 수량 한 번에 반환 |
| sinh(κT) < 1e-15 | TWAP 폴백: `x_j = X × (1 - j/N)` |

---

## 5. 마이크로 알파 모델

### 5.1 EWM Alpha (지수 이동평균 모멘텀)

> `src/layer1_signal/micro_alpha.py` — `EWMAlpha`

$$\text{fast\_ema}_t = \alpha_f \cdot P_t + (1 - \alpha_f) \cdot \text{fast\_ema}_{t-1}$$

$$\text{slow\_ema}_t = \alpha_s \cdot P_t + (1 - \alpha_s) \cdot \text{slow\_ema}_{t-1}$$

$$\text{raw} = \frac{\text{fast\_ema}}{\text{slow\_ema}} - 1$$

$$\text{score} = \tanh(\text{raw} \times 100)$$

여기서 $\alpha_f = \frac{2}{f+1}$, $\alpha_s = \frac{2}{s+1}$

| 파라미터 | 기본값 |
|---------|-------|
| fast_span (f) | 5 |
| slow_span (s) | 20 |

### 5.2 Order Flow Alpha (주문 흐름 불균형)

> `src/layer1_signal/micro_alpha.py` — `OrderFlowAlpha`

$$\text{imbalance} = \frac{\text{bid\_depth} - \text{ask\_depth}}{\text{bid\_depth} + \text{ask\_depth}}$$

$$\text{smoothed} = \text{mean}(\text{buffer}_{t-w:t})$$

$$\text{score} = \begin{cases} 0 & \text{if } |\text{smoothed}| < \theta \\ \tanh(\text{smoothed} \times 3) & \text{otherwise} \end{cases}$$

| 파라미터 | 기본값 | 의미 |
|---------|-------|------|
| imbalance_threshold (θ) | 0.2 | 데드밴드 임계값 |
| window (w) | 5 | 이동평균 윈도우 |

### 5.3 Spread Alpha (스프레드 압축)

> `src/layer1_signal/micro_alpha.py` — `SpreadAlpha`

$$\text{relative} = \frac{\text{spread\_bps}}{\text{avg\_spread}}$$

$$\text{score} = 1.0 - \text{relative}$$

넓은 스프레드 페널티 ($\text{spread\_bps} > W$):

$$\text{score} -= \min\left(\frac{\text{spread\_bps} - W}{W},\ 1.0\right)$$

| 파라미터 | 기본값 |
|---------|-------|
| window | 20 |
| wide_spread_bps (W) | 30.0 |

- 최종 score를 [-1, 1]로 클리핑

### 5.4 앙상블 (MicroAlpha)

$$\text{composite} = \sum_i w_i \cdot \text{score}_i$$

신뢰도 추정:

$$\text{confidence} = \overline{|\text{score}_i|} \times \left(1 - \sqrt{\text{Var}(\text{score}_i)}\right)$$

기대수익률 (플레이스홀더):

$$\text{expected\_return} = \text{composite} \times 10.0 \quad [\text{bps}]$$

---

## 6. 신뢰도 추정

> `src/layer1_signal/confidence.py` — `ConfidenceEstimator`

$$\text{raw\_conf} = \overline{|s_i|} \times \max(0,\ 1 - \text{std}(s_i)) \times (1 - w_e \cdot H_{\text{norm}})$$

정규화 엔트로피:

$$H_{\text{norm}} = \frac{-\sum_k p_k \log_2 p_k}{\log_2 B}$$

여기서 B = 5 (이산화 빈 수), $s_i$ = 시그널 점수들

레짐 배수:

| 레짐 | 배수 |
|------|------|
| HIGH_VOL | × 0.7 |
| ILLIQUID | × 0.5 |
| market_open | × 0.6 |
| pre_close | × 0.75 |
| halted | × 0.0 |

$$\text{confidence} = \text{clip}\bigl(\text{raw\_conf} \times \text{regime\_mult},\ 0,\ 1\bigr)$$

| 파라미터 | 기본값 |
|---------|-------|
| min_history | 20 |
| entropy_weight ($w_e$) | 0.3 |

### Signal Gate (시그널 필터)

통과 조건 (모두 충족 시):
1. `signal.is_valid == True`
2. `|signal.score| ≥ min_score_abs` (기본 0.1)
3. `signal.confidence ≥ min_confidence` (기본 0.3)
4. 세션이 허용 목록에 포함
5. halted 상태가 아님

---

## 7. 시그널 정규화

> `src/layer1_signal/signal_norm.py`

### Z-Score (기본값)

$$z = \frac{x - \mu}{\sigma}, \quad \text{clipped} = \text{clip}(z, -c, c), \quad \text{output} = \frac{\text{clipped}}{c}$$

### Rank

$$\text{output} = \text{percentile\_rank}(x) \times 2 - 1$$

### MinMax

$$\text{output} = 2 \times \frac{x - \min}{\max - \min} - 1$$

### Robust (MAD 기반)

$$z = \frac{x - \text{median}}{Q_{75} - Q_{25}}, \quad \text{output} = \frac{\text{clip}(z, -c, c)}{c}$$

| 파라미터 | 기본값 |
|---------|-------|
| method | "zscore" |
| window | 252 |
| clip_std (c) | 3.0 |

- 모든 방법의 출력 범위: [-1, 1]

---

## 8. 리스크 메트릭

> `src/layer6_evaluator/risk_metrics.py`

### 변동성 (연환산)

$$\sigma_{\text{ann}} = \sigma_{\text{period}} \times \sqrt{F}$$

여기서 F = 연환산 인수 (일간: 252, 분간: 252 × 390)

### Sharpe Ratio

$$\text{Sharpe} = \frac{\bar{r}_{\text{ann}}}{\sigma_{\text{ann}}}$$

(무위험수익률 = 0 가정)

### Sortino Ratio

$$\text{Sortino} = \frac{\bar{r}_{\text{ann}}}{\sigma_{\text{downside,ann}}}$$

$$\sigma_{\text{downside}} = \text{std}(r_t \mid r_t < 0)$$

### Calmar Ratio

$$\text{Calmar} = \frac{\bar{r}_{\text{ann}}}{\text{MDD}}$$

### Maximum Drawdown (MDD)

$$\text{peak}_t = \max_{s \leq t} V_s, \quad \text{DD}_t = \frac{\text{peak}_t - V_t}{\text{peak}_t}, \quad \text{MDD} = \max_t \text{DD}_t$$

### Value at Risk (VaR)

$$\text{VaR}_\alpha = -\text{percentile}\bigl(r,\ (1-\alpha) \times 100\bigr)$$

- VaR 95%: 5th percentile
- VaR 99%: 1st percentile
- 양수 = 손실 크기

### Expected Shortfall (CVaR)

$$\text{ES}_\alpha = -\text{mean}\bigl(r_t \mid r_t \leq -\text{VaR}_\alpha\bigr)$$

### 고차 모멘트

- **Skewness**: Fisher's definition
- **Kurtosis**: 초과 첨도 (정규분포 = 0)

---

## 9. 실행 품질 메트릭

> `src/layer6_evaluator/execution_metrics.py`

### Implementation Shortfall (IS)

$$\text{IS}_{\text{bps}} = \frac{\sum (\text{fill\_price}_i - \text{arrival\_price}) \times Q_i}{\sum \text{arrival\_price} \times Q_i} \times 10{,}000$$

(SELL인 경우 분자의 부호 반전)

### Fill VWAP

$$\text{VWAP}_{\text{fill}} = \frac{\sum \text{fill\_price}_i \times Q_i}{\sum Q_i}$$

### Market VWAP (프록시)

$$\text{VWAP}_{\text{market}} = \frac{\sum \text{mid}_t \times \text{depth}_t}{\sum \text{depth}_t}$$

### VWAP Difference

$$\text{vwap\_diff\_bps} = \frac{\text{VWAP}_{\text{fill}} - \text{VWAP}_{\text{market}}}{\text{VWAP}_{\text{market}}} \times 10{,}000$$

### Timing Score

각 체결 시점의 20기간 이동평균 mid와 비교:
- BUY: `fill_price ≤ avg_mid` → 좋은 체결
- SELL: `fill_price ≥ avg_mid` → 좋은 체결

$$\text{timing\_score} = \frac{\text{good\_fills}}{\text{total\_fills}} \in [0, 1]$$

### 참여율

$$\text{participation\_rate} = \text{mean}\left(\frac{\text{fill\_qty}_i}{\text{market\_depth}_i}\right)$$

---

## 10. 성과 귀인 분석

> `src/layer6_evaluator/attribution.py`

### 분해 구조

$$\text{Total PnL} = \text{Alpha} + \text{Execution} + \text{Cost} + \text{Timing} + \text{Residual}$$

| 항목 | 계산 방식 |
|------|---------|
| **Alpha** | 모든 체결가를 arrival_price로 대체 후 FIFO PnL 재계산 |
| **Cost** | $-(\text{total\_fees} + \text{total\_slippage\_KRW})$ |
| **Timing** | $\frac{\overline{\text{TWAP\_IS}} - \text{actual\_IS}}{10{,}000} \times \text{total\_notional}$ |
| **Execution** | $\text{Total} - \text{Alpha} - \text{Cost} - \text{Timing}$ |
| **Residual** | $\text{Total} - (\text{Alpha} + \text{Execution} + \text{Cost} + \text{Timing})$ |

TWAP 벤치마크 IS:

$$\text{TWAP\_price} = \text{mean}(\text{mid}_{t_1}, \ldots, \text{mid}_{t_n})$$

$$\text{TWAP\_IS}_{\text{bps}} = \frac{\text{TWAP\_price} - \text{arrival\_price}}{\text{arrival\_price}} \times 10{,}000$$

Timing 양수 = TWAP보다 우수한 타이밍

---

## 11. 레이턴시 모델

> `src/layer5_simulator/latency_model.py`

### 확률적 레이턴시

$$\text{latency} = \max\bigl(0,\ \text{base\_ms} + \mathcal{N}(0, \sigma_j)\bigr)$$

| 프로파일 | submit | ack | cancel | data_delay | (단위: ms) |
|---------|--------|-----|--------|------------|-----------|
| **기본값** | 0.5 | 1.0 | 0.3 | 0.2 | |
| **colocation** | 0.05 | 0.15 | 0.05 | 0.05 | |
| **retail** | 5.0 | 15.0 | 3.0 | 2.0 | |
| **zero** | 0.0 | 0.0 | 0.0 | 0.0 | |

| 파라미터 | 기본값 |
|---------|-------|
| add_jitter | True |
| jitter_std_ms ($\sigma_j$) | 0.1 |

왕복 시간: `sample_submit_latency() + sample_ack_latency()`

---

## 12. 리스크 제한

> `src/layer2_position/risk_caps.py`

### 제약 조건

| 제약 | 수식 | 기본값 |
|------|------|-------|
| 총 노출 | $\sum \|N_i\| \leq L_{\text{gross}}$ | 1억 KRW |
| 순 노출 | $\|\sum N_i\| \leq L_{\text{net}}$ | 5천만 KRW |
| 단일 종목 | $\max(\|N_i\|) / V \leq P_{\text{max}}$ | 10% |
| 레버리지 | $\sum \|N_i\| / V \leq \lambda_{\text{max}}$ | 2.0x |
| 일일 회전율 | $\text{turnover} \leq T_{\text{max}}$ | 50% |

총 노출 초과 시 균등 스케일링:

$$\text{scale} = \frac{L_{\text{gross}}}{\sum |N_i|}$$

### 회전율 예산

> `src/layer2_position/turnover_budget.py`

$$\text{turnover} = \frac{\sum |\Delta Q_i| \times P_i}{V}$$

$$\text{cost} = \sum |\Delta Q_i| \times P_i \times \frac{\text{half\_spread\_bps}}{10{,}000} \times c_{\text{bps}}$$

| 파라미터 | 기본값 |
|---------|-------|
| daily_turnover_limit | 0.5 |
| cost_per_bps | 5.0 |
| max_cost_budget | 50.0 |
| min_holding_steps | 5 |
| half_spread (default) | 10.0 bps |

초과 시 스로틀링: `scale = limit / actual_turnover`, 델타에 균등 적용

---

---

## 14. 체결 시뮬레이션 (Matching Engine)

> `src/layer5_simulator/matching_engine.py`

### 대기열 모델별 접근 가능 수량

| 모델 | 대기열 비율 | 특성 |
|------|-----------|------|
| PRICE_TIME | $f = q$ | 선형 (표준 FIFO) |
| RISK_ADVERSE | $f = q$ | 보수적 추정 |
| PROB_QUEUE | $f = q^2$ | 이차 (낙관적) |
| PRO_RATA | $\frac{Q_{\text{order}}}{V_{\text{resting}} + Q_{\text{order}}}$ | 비례 배분 |
| RANDOM | $\text{Uniform}(0, V_{\text{trade}})$ | 균일 랜덤 |

여기서 $q$ = queue_position_assumption (기본 0.5)

### 시장가 주문 체결

- **NO_PARTIAL_FILL**: best_ask/bid에서 전량 즉시 체결
- **PARTIAL_FILL**: 호가창을 순회하며 가능한 만큼 체결, 가중평균가 반환

### 교차 지정가 체결 (Crossing Limit)

$$\text{avg\_price} = \frac{\sum \text{fill\_qty}_l \times P_l}{\sum \text{fill\_qty}_l}$$

호가 레벨을 순회하며 주문 수량이 소진될 때까지 체결

---

## 15. Strategy Spec 컴파일러 모델

> `src/strategy_compiler/compiler.py` — `CompiledStrategy`

### Signal Score 계산

$$\text{score} = \sum_{i} \begin{cases} c_i & \text{if } f_i \odot \theta_i \text{ is true} \\ 0 & \text{otherwise} \end{cases}$$

여기서:
- $f_i$: 피처 값 (예: `order_imbalance`)
- $\odot$: 비교 연산자 (`>`, `<`, `>=`, `<=`, `==`, `cross_above`, `cross_below`)
- $\theta_i$: 임계값
- $c_i$: `score_contribution` (양수 = 매수, 음수 = 매도)

### Cross Above/Below

$$\text{cross\_above}(f, \theta) \iff f_{t-1} \leq \theta < f_t$$
$$\text{cross\_below}(f, \theta) \iff f_{t-1} \geq \theta > f_t$$

### Filter 모델

각 필터 조건이 트리거되면:
- `action = "block"`: 시그널 생성 건너뜀
- `action = "reduce"`: 스코어를 절반으로 감소

### Exit 모델

| Exit Type | 트리거 조건 |
|-----------|-----------|
| stop_loss | $\text{pnl\_bps} < -\|\text{threshold}\|$ |
| take_profit | $\text{pnl\_bps} > \|\text{threshold}\|$ |
| trailing_stop | $\text{drawdown\_bps from peak} > \|\text{threshold}\|$ |
| time_exit | $\text{ticks\_held} \geq \text{timeout}$ |
| signal_reversal | 새 시그널의 방향이 현재 포지션과 반대 |

PnL 계산:

$$\text{pnl\_bps} = \frac{(\text{mid} - \text{entry\_price})}{\text{entry\_price}} \times 10{,}000 \times \text{direction}$$

---

## 16. Universe 집계 메트릭

> `scripts/summarize_universe_results.py`

종목 집합 $\{s_1, \ldots, s_N\}$에 대해:

$$\text{mean\_pnl} = \frac{1}{N} \sum_i \text{pnl}_i$$
$$\text{median\_pnl} = \text{median}(\text{pnl}_1, \ldots, \text{pnl}_N)$$
$$\text{std\_pnl} = \sqrt{\frac{1}{N-1} \sum_i (\text{pnl}_i - \overline{\text{pnl}})^2}$$
$$\text{win\_rate} = \frac{|\{i : \text{pnl}_i > 0\}|}{N}$$

Latency 축별로 동일 메트릭을 분리 계산하여 latency 민감도 분석에 활용
