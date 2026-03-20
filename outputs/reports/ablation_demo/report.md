# Experiment Report: reward_penalty_ablation

Generated: 2026-03-17 07:32:20

## Key Findings

- Best mean_val_sharpe: variant=both (mean=0.5114, CI=[0.4131, 0.6292])
- Best mean_val_pnl: variant=both (mean=234.3844, CI=[165.7145, 304.4747])
- inv_only vs no_penalty (mean_val_sharpe): delta=+0.1358 (higher), p=0.0182*, d=2.121

## Summary Statistics (95% Bootstrap CI)

| variant | Metric | N | Mean | Std | 95% CI | Median | IQM |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no_penalty | mean_val_sharpe | 5 | 0.3374 | 0.0835 | [0.2610, 0.3886] | 0.3602 | 0.3611 |
| no_penalty | mean_val_pnl | 5 | 123.5823 | 88.9902 | [64.2526, 199.0654] | 89.6956 | 101.3576 |
| inv_only | mean_val_sharpe | 5 | 0.4732 | 0.0350 | [0.4467, 0.4997] | 0.4668 | 0.4772 |
| inv_only | mean_val_pnl | 5 | 210.7386 | 94.0172 | [136.2745, 282.9934] | 205.0074 | 205.6191 |
| turn_only | mean_val_sharpe | 5 | 0.3218 | 0.0454 | [0.2869, 0.3562] | 0.3289 | 0.3177 |
| turn_only | mean_val_pnl | 5 | 142.1734 | 47.4360 | [105.5869, 178.7600] | 134.5471 | 145.2927 |
| both | mean_val_sharpe | 5 | 0.5114 | 0.1417 | [0.4131, 0.6292] | 0.4663 | 0.4796 |
| both | mean_val_pnl | 5 | 234.3844 | 89.6569 | [165.7145, 304.4747] | 199.3585 | 221.0135 |

## Pairwise Comparisons

| Group | vs Baseline | Metric | Mean (group) | Mean (baseline) | Delta | p-value | Sig. | Cohen's d |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| inv_only | no_penalty | mean_val_sharpe | 0.4732 | 0.3374 | +0.1358 | 0.0182 | * | 2.121 |
| turn_only | no_penalty | mean_val_sharpe | 0.3218 | 0.3374 | -0.0157 | 0.7245 | n.s. | -0.233 |
| both | no_penalty | mean_val_sharpe | 0.5114 | 0.3374 | +0.1739 | 0.0529 | n.s. | 1.495 |

---

*Statistical methods: bootstrap CI (10,000 resamples), Welch's t-test, Cohen's d effect size.*
