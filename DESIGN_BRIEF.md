# KEPLER — Briefs de diseño para Stitch
> Pegar estos prompts en Google Stitch (uno por pantalla). Generados 2026-06-03 para el rediseño del
> frontend (dashboard operativo + página de track record). **Orden:** primero el §0 (sistema de diseño),
> luego cada página. El MCP de Stitch (`.mcp.json`) deja que Claude integre el resultado en las páginas vivas.
>
> ⚠️ **Regla de oro del diseño Kepler:** elegante, profesional y de **confianza para inversores de alto
> capital** (estética de banca privada / gestión de patrimonio institucional). Sobriedad, NO casino: nada de
> ROI gigante en verde, cohetes, neón ni parpadeos. El diferenciador es "copy-lead honesto de **bajo
> drawdown**" → el estilo debe transmitir bajo-drama, rigor y solidez. Mostrar el maxDD con tanto orgullo
> como el retorno. **El tema puede ser claro U oscuro** — lo que prime es que se vea premium y confiable.

---

## §0 — Sistema de diseño (generar PRIMERO, exportar DESIGN.md)

```
Design an elegant, premium design system for a quantitative crypto investment platform called Kepler.
Audience: HIGH-NET-WORTH investors and the platform operator. Tone: trustworthy, calm, sophisticated,
data-first, low-drama — like a private-banking / institutional wealth-management product (think a top-tier
hedge-fund fact sheet, Stripe/Linear polish, a Bloomberg terminal's rigor). NOT a flashy crypto-casino.

Provide BOTH a light and a dark variant so we can choose; the priority is looking premium and confidence-
inspiring, not a specific hue.
Foundations:
- LIGHT variant: warm off-white/ivory background (~#FAFAF7), deep navy/charcoal text (~#14213D),
  hairline borders, soft subtle shadows. DARK variant: deep ink (~#0E1116) with elevated panels.
- A refined, restrained accent palette: one sophisticated primary (deep navy, muted teal #0E7C66, or a
  understated gold #B08D57 — pick what reads most "trust/wealth"), used sparingly.
- Color carries MEANING only — calm green for gains/healthy, restrained red for losses/critical, amber for
  warnings. No decorative gradients, no neon, no glow.
- Typography: an elegant transitional serif for headings (e.g. Newsreader / Source Serif) paired with a
  clean sans (Inter) for body, and tabular/monospaced figures for all numbers.
- Generous whitespace, clear hierarchy, rounded cards (10–14px radius), consistent 8px spacing grid,
  hairline dividers.
- Components: stat/KPI cards, data tables with tabular figures, line charts, a traffic-light status badge,
  pill badges, and tasteful disclaimers as first-class elements (not fine print).
Export the design system as tokens (colors for both variants, typography scale, spacing, radii).
```

---

## §1 — Dashboard operativo (interno, "sala de control")

```
Design an elegant operational dashboard for Kepler, a market-neutral crypto trading system. High information
density, scannable, real-time feel (auto-refreshing). Audience: the operator monitoring the live system.
Use the Kepler design system (light or dark per the chosen variant); keep it professional and uncluttered.

Layout, top to bottom:
1. Sticky header: logo "🛰️ KEPLER", a MODE badge (DEMO/REAL/DRY_RUN), a Tier badge, a Circuit-Breaker
   status badge (green "Operando" / red "HALT"), last-updated timestamp, and buttons (Track record, downloads).
2. A row of compact KPI stats: Equity, Total return, Today's return, Positions, Gross, Leverage, Sharpe
   (backtest), maxDD (backtest), Last cycle.
3. "System health" card — PROMINENT: a traffic-light list of automated checks, each with a green/amber/red
   dot, a label (Data coverage, Data freshness, Leverage, Concentration, # positions, Dollar-beta, Sleeve
   correlation) and a short message. Plus a 30-day strip of small colored squares (one per day) showing the
   worst severity that day, and a one-line runtime/heartbeat status.
4. "Daily report" card: a one-line templated narrative + 8 small metrics (today return, drawdown, leverage,
   positions, top position, slippage median, cycles today, circuit breaker).
5. Equity curve (large line chart) and below it a Drawdown chart (filled red area, max 0).
6. Two side-by-side cards: a doughnut chart "Diversification by strategy" (7 sleeves) and a bar chart
   "PnL per position".
7. "Active positions" card: long/short/net dollar chips + a table (symbol, side, USD, PnL).
8. "Daily returns" table (day, closing equity, day return, drawdown).
9. "System logs" card: filterable list (All/Info/Warnings/Errors/Critical), monospaced.

Charts are placeholders — they will be wired to live data later. Keep it calm and dense, like a cockpit.
```

---

## §2 — Track record público (inversor, "tear-sheet")

```
Design an elegant, premium public track-record page for Kepler, a market-neutral crypto fund strategy.
Audience: HIGH-NET-WORTH prospective investors / copy-trading followers — the design must inspire trust and
look like a top-tier wealth-management / hedge-fund fact sheet (AQR / Two Sigma / Bridgewater vibe): calm,
honest, sophisticated. NOT a crypto-casino: no giant green ROI, no rockets, no neon, no flashing. Use the
Kepler design system (a refined LIGHT variant likely reads most premium here, but follow the system). Lots
of whitespace, elegant serif headings, hairline rules.

Layout, top to bottom:
1. Header: logo "🛰️ KEPLER", an amber badge "DEMO · track en construcción", last-updated timestamp.
2. "Summary" card: one short honest paragraph (templated text).
3. Hero KPIs (live, DEMO): Total return, Realized Sharpe (with a small "ref. backtest 2.07" subline),
   Max drawdown (with a "budget −10%" subline), Positive months, Beta vs BTC (≈0 = market-neutral), Days live.
   Make these the focal point, but understated and elegant — NOT oversized green numbers.
4. Large, clean equity curve (DEMO).
5. "Secondary metrics" card: Annualized return* (with "*noisy on few days" note), Realized Sortino,
   Annualized volatility, Positive days, Positions, Gross.
6. "Monthly returns" — a heatmap / table (month, return; green positive, red negative, muted).
7. "How risk is managed" card: explain market-neutral (β≈0), 7 decorrelated strategies, daily rebalance,
   NO per-trade stop-loss, portfolio-level risk + a circuit breaker at −20%. Then an HONEST disclaimer
   block (amber, prominent — not fine print): currently DEMO; the metrics are REAL live performance, not
   backtest; backtest figures are reference only, not a promise; a short track is noisy and value accrues
   over time. Show the maxDD as proudly as the return.
8. Minimal footer with a link back to the operational panel.

Charts are placeholders — they will be wired to live data later. The restraint is the brand.
```

---

## Notas de integración (para Claude, tras exportar de Stitch)
- Las gráficas se mantienen en **Chart.js** (datos vivos de `/api/equity`, `/api/track`, etc.), solo
  re-estilizadas a los tokens del `DESIGN.md`. Los mocks de Stitch son placeholders.
- Conservar el **bucle de fetch + auto-refresh** y el cableado a los endpoints existentes
  (`/api/status`, `/api/health`, `/api/daily_report`, `/api/positions`, `/api/track`, `/api/logs`).
- Mantener las páginas **autocontenidas** y servibles como HTML estático desde FastAPI (la VM las sirve así).
  Si Stitch usa Tailwind por CDN, verificar que cargue; si se quiere robustez offline, inlinear estilos.
- No introducir métricas que el backend no produzca: el diseño se adapta a los datos reales, no al revés.
```
