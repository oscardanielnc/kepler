# KEPLER — Market-neutral quantitative trading system (Binance USD-M Futures)

An autonomous, market-neutral portfolio engine that researches, validates, sizes, executes and audits a
long/short book of ~13–19 crypto perpetual futures — with the whole decision chain reconstructable from a
SQLite audit trail.

**Status: archived 2026-06-26.** It ran unattended with **real money** for 18 days before being shut down —
not because the engineering failed, but because the *business model* around it didn't hold. That post-mortem is
[§8](#8-post-mortem-why-a-working-system-was-shut-down), and it is deliberately the most detailed section of
this README.

```
Author    Oscar Navarro  ·  oscar@pairus.ai
Language  Python 3.11 (pandas / numpy / statsmodels / FastAPI / SQLite)
Scope     ~3.8k LOC production  ·  ~13k LOC research (102 experiment scripts)  ·  138 commits over 4 weeks
Live      Oracle Cloud VM · systemd · FastAPI dashboard · push alerts · 18 days real capital, 0 crashes
```

> **Note for reviewers:** the in-repo engineering docs (`STATUS.md`, `LESSONS.md`, `ROADMAP.md`, `SYSTEM.md`)
> are written in Spanish — they are the working record, not a showcase. This README is the English entry point
> and is self-contained. Every number below is traceable to a script or a doc in this repo.

---

## Table of contents

1. [What the system does](#1-what-the-system-does)
2. [Why this repo is worth 15 minutes](#2-why-this-repo-is-worth-15-minutes)
3. [Architecture](#3-architecture)
4. [The research harness — how an edge earned its way into production](#4-the-research-harness--how-an-edge-earned-its-way-into-production)
5. [Risk framework](#5-risk-framework)
6. [Execution and live operations](#6-execution-and-live-operations)
7. [Results — backtest vs. reality](#7-results--backtest-vs-reality)
8. [Post-mortem: why a working system was shut down](#8-post-mortem-why-a-working-system-was-shut-down)
9. [Repository map](#9-repository-map)
10. [Running it](#10-running-it)

---

## 1. What the system does

Kepler holds a **dollar- and beta-neutral** book of crypto perpetual futures and rebalances it **once every 24
hours**. It combines **seven independently validated return predictors ("sleeves")** whose pairwise correlations
are ≈ 0, blends them by volatility parity, neutralizes the book's exposure to BTC, and sizes the whole thing so
that the *backtested maximum drawdown* hits a fixed target.

The seven sleeves, all cross-sectional over the perp universe unless noted:

| # | Sleeve | Signal | Validated in |
|---|--------|--------|--------------|
| 1 | XS-Momentum 30d | 30-day relative return, long winners / short losers | `research/e12_xsmom_validate.py` |
| 2 | XS-Reversal 60d | 60-day mean reversion | `research/e2_cross_sectional.py` |
| 3 | Low-vol 14d | short realized vol, long low-vol names | `research/e14_more_sleeves.py` |
| 4 | Carry | funding-rate differential (7-day smoothed to cut turnover) | `research/e4_carry.py`, `e19_carry_turnover.py` |
| 5 | Trend | long-only EMA20/EMA100 regime filter | `research/e10_trend.py` |
| 6 | Taker-flow 5d | buyer/seller aggression imbalance from taker volume | `research/e16b_orthogonal_sleeves.py`, `e16c` |
| 7 | HL-position 14d | position within the 14-day high/low channel | `research/e16d_round3_sleeves.py`, `e16e` |

**There are no per-trade stop-losses or take-profits.** Risk is managed at the portfolio level:
diversification across uncorrelated sleeves, exact daily β-neutralization, position concentration caps, an
equity-drawdown circuit breaker, and drawdown-anchored leverage. A position lives for as long as its signal
persists and is reduced, flipped or closed when the signal changes — the rebalance *is* the risk management.

The design deliberately rejects intraday activity: the edges are multi-day, and faster rebalancing was measured
to die on transaction costs (`research/e54_rebalance_timing.py`, `e44_intraday_cost.py`, `INTRADAY.md`).

---

## 2. Why this repo is worth 15 minutes

If you only read three things, read these — they show judgement, not just code:

1. **[`LESSONS.md`](LESSONS.md)** — the closing retrospective. What was reusable, what was learned, and the
   strategic mistake that killed the project, written without varnish.
2. **[`kepler/portfolio.py`](kepler/portfolio.py)** — 120 lines that invert the usual risk dial: instead of
   picking a leverage and observing the drawdown, you *declare the drawdown budget* and the leverage is solved
   for by bisection, then made robust against the data window.
3. **[`research/e29_purged_walkforward.py`](research/e29_purged_walkforward.py)** and
   **[`research/e20_deflated_sharpe.py`](research/e20_deflated_sharpe.py)** — purged/embargoed walk-forward and
   the Deflated Sharpe Ratio, i.e. the machinery whose *only purpose is to make our own numbers smaller and
   more honest*.

What this project demonstrates, concretely:

- **Engineering discipline under uncertainty.** A hard rule, written into the repo's own contributing guide
  (`CLAUDE.md`): *nothing reaches production without a backtest showing it improves return and/or reduces
  risk.* It was enforced against the author's own ideas repeatedly, and it killed most of them (§4.3).
- **Statistical honesty as a feature.** Deflated Sharpe, purged walk-forward with embargo, combinatorial purged
  CV, leave-one-out fragility testing, liquidity-dependent slippage, taker-cost stress tests, and a product-level
  gate that *refuses to publish a Sharpe ratio* until N ≥ 30 days.
- **Production operations, not a notebook.** systemd services, incremental data refresh, pre-trade safety
  checks that can veto a rebalance, a circuit breaker, push alerting, a live dashboard, and an append-only
  audit log that can reconstruct why any position existed at any point in time.
- **Incident response.** Three real production incidents (an over-leveraged VM from a missing backfill, a
  demo-account expiry that made the balance unreadable mid-cycle, and a wallet-vs-mark-to-market equity bug)
  were each diagnosed, fixed, and converted into a permanent guard. See §6.3.
- **Knowing when to stop.** After ~80 experiments the marginal alpha ran out and the business case did not
  close. The project was archived with a clean teardown and a written retrospective instead of being kept
  alive out of sunk cost.

---

## 3. Architecture

```
config.py                universe · fee model · risk limits · timezone · product gates
   │
   ▼
kepler/fetch.py          bulk history + incremental refresh (data.binance.vision → parquet store)
   │
   ▼
kepler/alphas.py         7 sleeve signal generators (pure functions over price/volume/funding panels)
   │
   ▼
kepler/portfolio.py      vol-parity blend · metrics · leverage_for_maxdd_anchor · leverage_robust
   │
   ▼
kepler/engine.py         THE BRAIN: compute_target(tier) → target weight vector, β-neutral, capped
kepler/lowbarrier.py     low-barrier book variant (cheap-coin universe, internal β re-neutralization)
   │
   ▼
kepler/checks.py         pre-trade guards (data coverage, freshness, leverage band, β, gross) → OK/WARN/CRIT
   │
   ▼
kepler/execution.py      maker-first rebalancing (LIMIT GTX), no-fill management, capital-aware leg dropping
kepler/circuit_breaker.py  halt on equity drawdown from peak; auto-resume on recovery
   │
   ▼
kepler/orchestrator.py   THE LOOP: 15-min heartbeat (equity) · 24-h rebalance · reconcile · audit
   │
   ├── kepler/db.py      SQLite: signals · trades · portfolio_snapshot · equity_daily · shadow_signal ·
   │                     daily_report · audit_event  (source of truth + auditability + JSON export)
   ├── kepler/notify.py  ntfy.sh push (cycle, error, halt, escalation)
   ├── kepler/report.py  6-panel matplotlib daily report
   ├── kepler/track.py   realized track-record metrics with a maturity gate
   ├── kepler/monitor.py operational health scoring
   ├── kepler/onchain.py DefiLlama/on-chain fetcher + shadow-signal writer
   └── kepler/api/       FastAPI (status/positions/equity/track/health/logs) + single-page dark dashboard
```

Two design choices carried the most weight:

**SQLite as the source of truth, not as a cache.** Every signal (with a JSON feature snapshot), every trade,
every portfolio snapshot and every system event is written before anything else happens. Any decision the
system ever made can be replayed and explained after the fact — which is what turned each production incident
from a mystery into a 20-minute diagnosis.

**Shadow signals.** Candidate sleeves that were not yet trusted enough to trade were still computed and stored
**point-in-time, every cycle**, in a `shadow_signal` table (`kepler/onchain.py`). This produces an honest
out-of-sample record for data that cannot be re-requested later (on-chain series get silently revised), and it
is how the on-chain candidates were ultimately evaluated at shutdown — with 1,932 recorded shadow observations
rather than a hopeful backtest.

---

## 4. The research harness — how an edge earned its way into production

`research/` holds **102 numbered experiments** (`e1` … `e83`). They are not exploratory notebooks: each is a
runnable script with a docstring stating the hypothesis, the falsification criterion, and the verdict. The
harness itself is edge-agnostic and is the most portable asset in the repo.

### 4.1 Validation gates a candidate had to clear

| Gate | Implementation |
|------|----------------|
| **Purged walk-forward + embargo** | Weights *and* leverage fit on past data only, applied to an unseen block, with a gap to kill temporal leakage — `e29_purged_walkforward.py` |
| **Combinatorial purged CV (CPCV)** | Multiple train/test path combinations, not one lucky split — `e72`, `e37`, `e79` |
| **Deflated Sharpe Ratio** | Bailey & López de Prado: discounts the selection bias of having tried N configurations — `e20_deflated_sharpe.py` |
| **Realistic costs** | Maker 1.8 bps / taker 4.5 bps (BNB-discounted) **plus** liquidity-dependent slippage `50/√ADV_M` clipped to 0.5–30 bps, charged against measured turnover — `e18_slippage.py`, `e21_fill_slippage.py` |
| **Taker stress** | Nothing was promoted unless it survived being charged full taker fees — every `*_stress` script |
| **Leave-one-out fragility** | Remove each symbol, measure Δ; an "edge" that lives in one coin is not an edge — `e66_mvrv_stress.py`, `e17b`, `e30b` |
| **Thin-coin / illiquidity screen** | Symbols whose edge doesn't pay for its own slippage get removed from the universe — `e53_thin_coins.py`, `e30_illiquidity_check.py` |
| **Orthogonality** | A new sleeve had to be ≈uncorrelated with the existing seven to earn a slot — `e16b_orthogonal_sleeves.py`, `e38_crossfamily_blend.py` |

### 4.2 Things the harness measured that most retail systems never do

- **Fill quality in production, not in theory.** Maker GTX fills were measured at ~1 bps median slippage on
  incremental rebalances; building the book from flat cost a one-off ~6 bps (`e21`, `e55_slicing.py`).
- **Rebalance timing.** Crypto liquidity follows the US/EU clock; pinning the daily rebalance to 14:00 UTC
  (the liquidity peak, ~1.5× average) cut slippage ~21% for free — `e54_rebalance_timing.py`.
- **Minimum-notional as a structural constraint.** Binance's per-symbol minimum notional × number of legs sets
  a hard capital floor for the book — and, in the copy-trading business model, the *client's* entry barrier.
  This was quantified before funding (`e76`/`e77`, `kepler/lowbarrier.py`) and drove a full redesign of the
  traded universe.

### 4.3 The rule of gold, and what it killed

> *Proposal → backtest of the whole system → implement only if it improves return and/or reduces risk.
> Nothing reaches production without the numbers confirming the improvement.*

Ideas rejected by their own backtests — including several the author personally wanted to be true:

- **Pairs / statistical arbitrage**, short-horizon reversal, BTC→alt lead-lag timing, absolute cash-and-carry:
  all failed walk-forward (`e5_statarb.py`, `e1_dominance.py`, `e1b_leadlag_5m.py`).
- **Regime gating and carry-breadth filters** — intuitively appealing, made drawdown *worse* (`e31_regime_sweep_current.py`).
- **Fractional Kelly sizing** — insufficient sample to estimate the inputs; rejected as false precision.
- **Long bias for "a green curve every day"** (`e81_long_biased_steady.py`): tested a full dial from neutral to
  100% long. It added **zero** additional green days (green-day frequency in crypto is ≈ a coin flip regardless),
  cut returns 3–5×, and went negative through the 2022 bear market. The finding that closed the discussion:
  *"green every day" is not a strategy, it is a fee structure* — high-water-mark performance fees look green
  because they only charge at new highs, while the underlying curve has red days like everyone else's.
- **Small-take-profit trend scalping** (`e83_scalp_trend_tpsl.py`): hourly OHLC, real taker costs, pessimistic
  intrabar fills, benchmarked against **random direction entries**. Net expectancy was negative in every
  parameter combination and every year (−14 to −21 bps per trade) and statistically indistinguishable from
  random. A 60% win rate with a 0.34–0.62 payoff ratio is not an edge; it is the *illusion* of one.
- **Averaging down / hold-until-reversal**: identified as the same short-volatility, martingale signature —
  wins almost always, then loses everything once.

Documenting refuted ideas as first-class artifacts, with the script that refuted them, is the point. It is how
the next project avoids re-litigating them.

---

## 5. Risk framework

### 5.1 Drawdown as the budget, leverage as the output

The usual approach picks a leverage multiplier and hopes the drawdown is acceptable. Kepler inverts it: the
product tier **declares a maximum-drawdown budget**, and the leverage that pins the backtest to exactly that
drawdown is solved for numerically (`leverage_for_maxdd_anchor`, monotone → bisection, hard cap 4×).

| Tier | maxDD budget | Leverage | Return (walk-forward OOS, real costs — `e81`) |
|------|--------------|----------|-----------------|
| **ESTABLE** ← production | −10% | ~1.9× (solved) | +2.6%/month |
| BALANCEADO | −20% | solved, capped 4× | +6.3%/month |
| GROWTH | −30% | ~3.1× (solved) | +11.0%/month |

(The headline "+3.5%/month" quoted elsewhere in this repo is the in-sample full-history figure; the table above
is the stricter walk-forward out-of-sample vintage, and is the number that was used for decisions.)

The property that makes this worth the complexity: **every improvement in Sharpe converts into more return at
the same risk**, automatically, rather than into a quieter curve. Risk stays where the product promised it.

### 5.2 Making the anchor robust

A drawdown anchor fitted on a calm data window over-leverages. This was not a theory — a VM that was missing
its 2022 backfill computed 2.93× instead of 2.16× and took a −13% real drawdown. Two fixes, both validated:

- **`leverage_robust` = min(drawdown-anchor, vol-anchor) × haircut, capped** (`e68`). Realized volatility is
  far more stable across windows than max drawdown, so the vol anchor holds the line when history is short.
  Belt and braces: it can only ever *lower* leverage.
- **A data-coverage pre-trade check** (`kepler/checks.py`) that raises CRIT and blocks the rebalance outright
  if the panel does not extend back far enough — the guard that would have prevented the incident.

### 5.3 Neutrality, in layers

- **Exact β-neutralization**, daily: weights are projected so `Σ wᵢβᵢ = 0` against BTC (168-hour rolling β).
- **Partial net-dollar neutralization** (`λ_net`): the long-only trend sleeve leaves a residual net-dollar
  tilt. A two-constraint projection cancels a fraction λ of it *while preserving β = 0*. λ was walk-forward
  tuned over 13 folds (`e79`), and re-validated on live data when the observed tilt drifted (`e82`: 0.25 → 0.35
  beat the incumbent on return, drawdown and green-day count across both data vintages and both cost levels).
  λ = 0.50 produced more return but an unstable drawdown across vintages — so it was **not** deployed.
- **Concentration caps**: 25% per asset per sleeve, and a 15%-of-equity cap on the *combined* book, added after
  a name accumulated 23% of equity by appearing in three sleeves at once (`e69`).
- **Circuit breaker**: halts trading if equity falls 20% from its peak, resumes on recovery, evaluated on the
  15-minute heartbeat rather than at rebalance time.

### 5.4 Statistical honesty as a product rule

`TRACK_MIN_DAYS_RATIOS = 30`: annualized ratios (Sharpe, Sortino) are **not published** below 30 days of track
record. With N = 4 the honest computation returns "Sharpe −26", which is noise dressed as information. Below
the threshold the UI shows "—"; maximum drawdown, total return, volatility and green-day share — all honest at
any N — are shown. A related pre-registered gate stated, *before seeing the data*, that a Sharpe of ~1.4
requires roughly **6 months for a t-stat ≥ 1 and ~2 years for p < 0.05** — so neither a good week nor a bad
week would be allowed to change the decision.

---

## 6. Execution and live operations

### 6.1 Execution layer

`kepler/execution.py` speaks the Binance USD-M Futures REST API directly (HMAC-signed), with three modes
selected by environment variable and defaulting to the safe one:

```
KEPLER_DRY_RUN=true                  → log the orders, send nothing          (default)
KEPLER_DRY_RUN=false, USE_DEMO=true  → demo-fapi.binance.com
both false                           → fapi.binance.com (real money)
```

- **Maker-first**: `LIMIT` orders with `GTX` (post-only) time-in-force, so the book is never crossed by
  accident; unfilled orders are managed and retried rather than converted to market orders.
- **Capital-aware leg dropping**: the number of legs adapts to available equity so that every position clears
  Binance's minimum notional; dropped legs trigger a **β re-neutralization of the remainder**, so shrinking the
  book never silently introduces directional exposure.
- **Reconciliation**: target weights are diffed against actual exchange positions each cycle, not against an
  internal belief about them.

### 6.2 The loop

`orchestrator.py` runs a 15-minute heartbeat (equity capture, circuit breaker, health checks) and a 24-hour
rebalance pinned to 14:00 UTC, with `MIN_REBAL_HOURS`/`MAX_REBAL_HOURS` guards so a restart cannot trigger a
double rebalance and a missed window cannot leave the book unmanaged for more than 30 hours. A
`.force_rebalance` file flag allows a safe manual trigger without restarting the service.

### 6.3 Incidents, and the guards they produced

| Incident | Diagnosis | Permanent fix |
|---|---|---|
| VM ran at 2.93× instead of 2.16×, took a −13% drawdown | missing 2022 backfill → drawdown anchor fitted on a calm window | vol-anchor (`leverage_robust`) + CRIT-severity data-coverage pre-trade check |
| Demo account expired; balance reads returned garbage mid-cycle | equity source unreliable, would have produced fake equity points and churn | **skip the cycle, never trade on an unreadable balance** — plus an escalation alert after 3 consecutive skips, closing the "silently stopped trading" blind spot |
| Live drawdown looked better than it was | equity was read from wallet balance rather than mark-to-market | equity = `totalMarginBalance`; historical buggy days *labelled and excluded*, never deleted |

The governing principle, written down after the second one: **"better a gap in the curve than a false curve."**

### 6.4 Observability

FastAPI service (`kepler/api/`) exposing `/api/status`, `/positions`, `/equity`, `/track`, `/health`,
`/health/history`, `/daily_report`, `/logs`, `/download`, plus a dependency-free dark single-page dashboard
(Chart.js, 10-second refresh) and a public track-record page. Push notifications via ntfy.sh for cycle
completion, errors, halts and escalations. Daily 6-panel matplotlib report (equity, drawdown, sleeve
allocation, PnL, monthly heatmap) written to disk and downloadable.

---

## 7. Results — backtest vs. reality

**Backtest, 7 sleeves, full universe, walk-forward with real costs:**
Sharpe **1.94** · β **+0.03** · maxDD **−10%** (anchored by construction) · **~+3.5%/month** · 69% positive months.
The low-barrier production book (13 cheap perps, internal β-neutralization) held up: Sharpe **1.46–1.47**,
β ≈ −0.01, robust to 3× slippage and out-of-sample.

**Live, real money, 2026-06-09 → 2026-06-26 (18 days):**

| Metric | Live | Design target |
|---|---|---|
| Return | **−1.77%** ($298.18 → $292.91) | +3.5%/month |
| Max drawdown | **−3.4%** | −10% budget |
| Realized β | **+0.014** | ≈ 0 |
| Cycles completed | **14 / 14** | — |
| Errors / crashes | **0** | — |
| Transaction costs | trivial vs. modelled | — |

Read honestly: **−1.77% over 18 days is noise, not evidence.** At 13.5% annualized volatility the 1σ band over
that horizon is ±3.2%; the realization sits at −0.64σ against an expected +0.6%. It neither confirms nor refutes
the edge — and the pre-registered gate said exactly that in advance, which is why it did not trigger a panic
redesign. The risk machinery, however, *did* deliver measurably: drawdown came in at a third of budget and
β-neutrality held to within 1.4 basis points.

An earlier 9-day demo run of the full 20-symbol book returned −6.5%, traced to a net-long tilt from the trend
sleeve carrying the book through the June crash — which is precisely what the λ_net neutralization (§5.3) was
built and validated to fix.

---

## 8. Post-mortem: why a working system was shut down

The system worked. The product thesis did not. Three structural conflicts, none of which any Sharpe ratio could
have solved, and none of which were discovered by looking at the code:

**1. The business model was orthogonal to the research pipeline.** Kepler's commercial plan was to become an
honest low-drawdown *copy-trading lead*: publish a verifiable track record, attract followers, earn fees. For a
follower to mirror an 18-leg book, every leg must clear Binance's minimum notional — so the traded universe had
to be **cheap coins**. But the most promising remaining research vein was **on-chain data** (TVL, MVRV, address
activity), and that data only exists for **expensive coins** (BTC, ETH, BCH, LTC). The measurement is stark:
the MVRV valuation sleeve was worth **+2.15%/month on the broad universe** and **−0.40%/month** restricted to
the cheap-coin book. Every on-chain candidate was structurally doomed the moment it touched the universe the
business model required — and this was only discovered at the end.

**2. The product fought the psychology of its own market.** A flat, low-drawdown, market-neutral curve is
close to unsellable as a crypto copy-trading lead. The market chases visible ROI — which is why 20× martingale
accounts dominate the leaderboards until they blow up. The system's core virtues (survival, low drawdown,
β-neutrality) are not what the buyer is shopping for. Without followers there is no AUM; without AUM the
strategy manages micro-capital; a self-defeating loop.

**3. Micro-capital plus a long confirmation horizon has no economics.** On $293 of capital, even hitting the
backtested +3.5%/month is ~$10/month. The only real asset being built was the verifiable track record — and, by
the project's own pre-registered statistics, that record needed **6–18 months** to become statistically
meaningful. That was a cost the owner reasonably declined to fund on faith. Escalating to the GROWTH tier
(+11%/month backtested) was available and validated, but it would have added return *and* risk on top of an
edge that was still unconfirmed — more variance, not more certainty.

**The transferable lesson, stated in `LESSONS.md` as the project's epitaph:**

> The business model and the source of alpha must be **compatible from day one**, and verifying that is as
> critical as validating the edge itself. Map the question *"does my alpha source cover the universe my business
> forces me to trade?"* **before** building, not after 80 experiments.

**Teardown was executed properly**, not abandoned: all 10 open positions closed with reduce-only market orders,
account left flat with zero open orders, both systemd services stopped and disabled so they cannot restart, the
final database committed to this repository (`archive_final_2026-06-26/kepler_final.db` — 18 days of real
track, 46 trades, 1,932 shadow observations, 72 audit events) as evidence and out-of-sample data for any future
re-analysis, and a written
retrospective committed the same day.

---

## 9. Repository map

```
README.md            this file (English entry point)
LESSONS.md           ★ closing retrospective — reusable assets + what was learned (ES)
STATUS.md            live engineering log: daily state, changelog, open items — 195 KB of decisions (ES)
ROADMAP.md           improvement plan, research frontier, evaluated data sources with costs (ES)
SYSTEM.md            how the edge was validated + competitive analysis (ES)
MONITOREO.md         operations runbook: how to read the daily report, what to watch, known issues (ES)
COPYLEAD.md          copy-trading product research (ES)
INTRADAY.md          intraday frontier — analyzed, quantified, and deliberately shelved (ES)
DEPLOY.md            deployment procedure (ES)
PLAN.md / INSTRUCTIONS.md  original design documents (ES)
CLAUDE.md            engineering contract: the rule of gold, hard rules, reading order (ES)

config.py            universe · fee model · risk limits · product gates (heavily commented: every
                     constant records which experiment set it and why)
kepler/              production system (see §3)
research/            102 experiments, e1 … e83 — each with hypothesis, method and verdict
deploy.sh · setup_vm.sh · kepler.service · kepler-api.service    deployment
```

`config.py` deserves a specific look: nearly every constant carries the experiment ID that set it, the
alternative that was rejected, and the conditions under which it should be revisited. It is a decision log that
happens to be executable.

---

## 10. Running it

```bash
pip install -r requirements.txt

python -m kepler.fetch 1h                    # download the universe (data.binance.vision → parquet)
python -m kepler.db                          # initialize the SQLite schema

python -m kepler.engine ESTABLE              # compute the target portfolio (prints weights, β, leverage)
python -m kepler.backtest_portfolio          # backtest the combined book with real costs
python research/e29_purged_walkforward.py    # honest out-of-sample validation
python research/e20_deflated_sharpe.py       # selection-bias-adjusted Sharpe

python -m kepler.orchestrator ESTABLE --once # one full cycle (DRY_RUN by default — sends nothing)
python -m kepler.api                         # dashboard on :8080
```

**Safety defaults.** Execution is `DRY_RUN` unless explicitly disabled by environment variable, and demo
endpoints are preferred over live ones. No credentials are stored in the repository: API keys are read from the
environment (`/etc/kepler.env` on the deployment host, never committed). The account this system traded has
been closed and its keys revoked.

---

*Archived 2026-06-26. The code is preserved as-is at shutdown; the retrospective in `LESSONS.md` is the
handover document.*
