# Kepler

**A market-neutral, multi-asset quantitative trading system for crypto — built, validated, run on live capital, and then deliberately shut down.**

Kepler combined seven uncorrelated alpha "sleeves" into one portfolio, sized leverage against an explicit maximum-drawdown budget, and executed maker-only on Binance perpetuals. It ran unattended on real money for 18 days with zero production incidents, then was archived — not because it broke, but because the numbers said the business case did not work at the capital available.

The full post-mortem is in [`LESSONS.md`](LESSONS.md); the day-by-day record is in [`STATUS.md`](STATUS.md). This README is the short version.

**Status: archived 2026-06-26.** Not maintained. Kept public because the engineering and the shutdown decision are the interesting parts.

---

## What was actually measured

Two categories, kept strictly separate — which is the point of this section.

### Live, on real capital (18 days)

| | |
|---|---|
| Production incidents | **0** |
| Max drawdown | **−3.4%** against a −10% budget |
| Realized beta vs BTC | **+0.05** (tolerance ±0.10) — market-neutral held |
| Archived record | 18-day track + 1,988 logged shadow signals |

**No live Sharpe is published here, and that is deliberate.** Eighteen days is far below the system's own maturity gate (`TRACK_MIN_DAYS_RATIOS = 30`) for reporting risk-adjusted ratios. A Sharpe computed on N that small is noise wearing a number's clothes. A strategy with a true Sharpe near 1.4 needs roughly six months to reach t-stat ≥ 1 and about two years for p < 0.05 — so the honest thing to report from 18 days is drawdown control and beta, both of which held.

### Backtest, at the −10% drawdown anchor

| Cost model | Sharpe | Leverage | Return/month |
|---|---|---|---|
| Flat maker fee (engine default) | 1.94 | 1.92× | 3.52% |
| **+ ADV-based slippage (central, ~4bps)** | **1.67** | 1.77× | **2.70%** |
| + slippage ×3 (stress) | 1.18 | 1.22× | 1.21% |
| + 10bps flat (hard stress) | 1.34 | 1.37× | 1.57% |

**The honest number is ~1.67, not 1.94.** The engine charged a flat turnover fee and nothing at all on the trend sleeve, which understated real costs. Modelling slippage against actual liquidity ([`research/e18_slippage.py`](research/e18_slippage.py)) cost 0.82 points of monthly return. The 1.94 stayed in the engine because changing it would have lowered the anchor's leverage, but every downstream decision used 1.67.

The lever behind that gap is turnover: the carry sleeve reorders the book roughly every 48 hours on funding rank (199× capital/year, one-way), and trend was paying zero.

---

## Why it was shut down

Two structural conflicts, neither of them technical:

1. **The product was orthogonal to the market it was sold into.** A low-drawdown market-neutral book is close to unsellable as a copy-lead product — copiers buy the equity curve that goes vertical, not the one that survives. The virtue was invisible to the customer.
2. **The improvement path was structurally blocked.** New sleeves needed new signals, and the on-chain data that would have supplied them does not exist for the cheap, liquid perpetuals that made the strategy work in the first place. After ~80 experiments the marginal sleeves had stopped moving the needle.

At micro-capital, that combination means 6–18 months before the track record is worth anything to anyone. Killing a system that works is harder than killing one that doesn't, which is why the decision was made against the logged evidence rather than intuition.

---

## Design

```
config ──► fetch ──► db ──► alphas ──► portfolio ──► engine ──► execution
                      │                                            │
                      └──── audit trail ◄── circuit_breaker ◄───────┘
                                    │
              orchestrator ──► notify ──► report ──► api
```

**Orchestrator** — 15-minute heartbeat, 24-hour rebalance, restart-safe.

**Risk as a budget, not a dial.** The distinctive choice: `leverage_for_maxdd_anchor` fixes the maximum drawdown you are willing to accept and *derives* the leverage from it, instead of picking leverage and discovering the drawdown afterwards. Every Sharpe improvement then converts into more return at the same risk. The anchor also reacts to recent volatility, so leverage falls in a crash rather than converging on a fixed number.

**Neutralization.** Beta- and net-dollar-neutralization run separately, because they are not the same constraint — the live book sat 76% net long in dollars while realized beta stayed at +0.05, because the longs were low-beta assets and the trend sleeve is long-only by design. Confusing the two metrics is easy and I did it once mid-project; the correction is in `STATUS.md`.

**Equity is marked to market** (`totalMarginBalance`, never wallet balance), otherwise intraday drawdown is silently understated — which would have made the −3.4% look better than it was.

**Circuit breaker** on drawdown from peak equity, checked every cycle.

**Shadow signals.** Candidate sleeves that were not trading still logged, point-in-time and every cycle, the weights they *would* have taken (`shadow_signal` table). 1,988 of them by the end. It costs almost nothing and it is the only way to get honest out-of-sample validation on data you cannot request again later. The most reusable idea in the repo.

**Audit trail.** SQLite in WAL mode: signals, trades, portfolio state, equity curve, daily reports. Every decision is reconstructable after the fact — which is what made an evidence-based shutdown possible at all.

---

## Validation

- **Walk-forward** with **purged** out-of-sample windows and an **embargo** period, so overlapping labels cannot leak training information across the boundary.
- **Combinatorial purged cross-validation (CPCV)** for the sleeve combination, rather than one train/test split that any strategy can get lucky on once.
- Costs modelled explicitly — maker 0.018%, taker 0.045%, plus the ADV slippage model above.
- Stress scenarios at 3× slippage and 10bps flat, not just the convenient central case.
- **Maturity gates on reporting**: ratios are not published below 30 days of track record.

The seven surviving sleeves: cross-sectional momentum 30d, cross-sectional reversal 60d, low-vol 14d, carry (funding), trend EMA20/100, taker-flow 5d, HL-position 14d — pairwise correlation ≈ 0. An MVRV on-chain sleeve validated standalone (Sharpe 0.71) but could not be extended to the traded universe.

Most candidates died in this stage. That was the point of building it.

---

## Stack

Python · SQLite (WAL) · FastAPI + SPA dashboard · matplotlib reporting · ntfy push alerts · Binance market data (`data.binance.vision`) · systemd on an Oracle Cloud VM

## Layout

```
config.py                     universe, cost and risk assumptions
kepler/
  fetch.py                    resumable multi-asset downloader
  db.py                       SQLite: signals, trades, portfolio, equity, reports, audit
  portfolio.py                vol-parity combine, neutralization, maxDD anchor
  ...                         alphas, engine, execution, circuit breaker, orchestrator
research/                     sleeve studies and cost experiments
data/                         parquet store (futures_um, spot, funding)
archive_final_2026-06-26/     final database: live track + shadow signals + audit
LESSONS.md                    post-mortem
SYSTEM.md                     architecture detail
ROADMAP.md · INTRADAY.md      what was planned, and what intraday research found
```

---

> Educational and research code. Not financial advice, and not a system anyone should point at their own money.
