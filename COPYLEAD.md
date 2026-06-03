# KEPLER — Copy-lead (F2.3): requisitos, encaje y checklist
> Entregable de **ROADMAP §FASE 2 · F2.3** (investigar copy-trading como modelo de negocio).
> Investigado 2026-06-03. **El negocio de Kepler = ser lead honesto de bajo-DD → profit-share sobre AUM.**
> Esto NO depende de esperar a la DEMO: es research previo para tener el checklist listo cuando el track
> real lo respalde. ⚠️ Datos de plataformas cambian seguido — re-verificar antes de publicar.

---

## TL;DR — encaje
- ✅ **El bajo-maxDD es premiado en descubrimiento Y en profit-share** en todas las plataformas (Bybit
  rankea por maxDD/consistencia; Binance da más % con maxDD≤25%). El diferenciador de Kepler es exactamente
  el eje por el que pagan más → encaje de posicionamiento EXCELENTE.
- ✅ **El libro market-neutral multi-símbolo (long en unos, short en otros) ES copiable** como posiciones
  one-way proporcionales. NO es "hedge mode" (long+short del MISMO símbolo, que tiene reglas raras).
- ⚠️ El cuello de botella NO es elegibilidad (mínimos de lead triviales: ~500-1000 USDT) sino: (1) track
  real (Fase 0 = tiempo) y (2) que el libro sea **copiable LIMPIO** (ver cautelas mecánicas).

## Comparación de plataformas (2026-06)
| | Mín. lead | Profit-share | Mín. seguidor | Settlement | Nota Kepler |
|---|---|---|---|---|---|
| **Binance Futures** | ~500-1000 USDT | 10% def.; 15% si maxDD 90d ≤25%; Elite Trader más | 10 USDT | con HWM | Mayor liquidez; ecosistema grande |
| **Bybit** | por tier | Classic 10-15%; **Pro hasta 30% + HWM** | 100 USDT | semanal (T+6, NAV) | Ranking explícito por maxDD/consistencia/risk profile |
| **Bitget** | por tier | hasta 20% (Legend); 30% 14d nuevos | 50 USDT | — | Comunidad copy más grande (~190k traders) |
| **OKX** | — | hasta 30% comisión | 50 USDT | — | Métricas de riesgo detalladas en el perfil |

## Mecánica de la cuenta lead — ¿qué métricas se muestran? (re-verificar 2026-06)
- **NO es tu histórico personal.** En todas, el copy-lead opera desde un **portafolio/cuenta de "lead
  trading" DEDICADO**, separado de tu trading personal. Las métricas públicas (ROI, PnL, maxDD, AUM, días,
  win-rate) se calculan **desde que te das de alta como lead, sobre ESA cuenta** — no tus trades previos ni
  otras cuentas. ✅ **Ventaja para Kepler:** arranque limpio (el tramo con bug de la DEMO NUNCA toca el track
  real), y controlas exactamente qué capital/qué libro se mide. Binance: el lead usa un wallet de copy
  dedicado; el track = ese wallet desde el día 1 de lead.
- **¿Una o varias estrategias por cuenta?** Binance ≈ **un perfil de lead por cuenta** y **una cuenta por
  KYC** → no puedes correr 2 servicios independientes bajo la misma identidad; para 2 estrategias distintas
  harían falta 2 cuentas (difícil en una identidad) o 2 plataformas. Algunas (Bitget/OKX) históricamente
  permiten varios "portafolios/estrategias" por trader — **re-verificar**. Para Kepler da igual: hay **UNA
  estrategia** (7 sleeves), no necesitamos multi-estrategia.
- **¿Igual en todas?** El MODELO es el mismo (cuenta lead dedicada, métricas desde el inicio del lead). Lo
  que **difiere**: settlement, HWM, % de profit-share, mínimos y si permiten múltiples estrategias (ver tabla).
- **¿Solo Binance o varias plataformas?** Empezar con **UNA (Binance)**: mayor audiencia + el bot ya corre
  ahí. **El track NO se transfiere entre plataformas** — cada una se construye desde cero, con su propio
  capital y ops. Abrir en 2 a la vez = duplicar capital/atención y partir 2 tracks de cero. → **Probar en
  Binance primero; expandir a una 2ª (p.ej. Bybit Pro: hasta 30% + ranking por maxDD) cuando esté probado.**

## Cautelas mecánicas (lo que hay que diseñar en el libro)
1. **Fragmentación de margen en seguidores chicos.** Copy mínimo 10-100 USDT replicando ~20 posiciones →
   cada una minúscula → choca con el **mínimo notional por orden** en algunos símbolos → tracking error.
   - Mitigación: recomendar a seguidores el modo **Fixed Ratio** (NO Fixed Amount — Binance avisa que con
     muchas posiciones/rebalanceos el Fixed Amount se queda sin margen). Considerar variante "lite" con menos
     nombres para tickets chicos, o apuntar a seguidores con capital suficiente para replicar 20 posiciones.
2. **Turnover diario + fills del seguidor.** Rebalanceo diario en ~20 nombres = muchas órdenes copia; el
   seguidor suele entrar **taker** (vs nuestro maker-first GTX) → su slippage > el nuestro → su retorno < el
   track publicado. Comunicar este gap con honestidad (es parte del diferencial honesto).
3. **HWM = aliado del bajo-DD.** Preferir plataformas con High-Water Mark (Bybit Pro / Binance): no
   doble-cobran profit-share tras un drawdown → coherente con la promesa de bajo-DD y justo para el seguidor.

## CHECKLIST para activar copy-lead (cuando el track real lo respalde)
- [ ] **Track record real** en DEMO→REAL: ≥3-6 meses, Sharpe/maxDD/β vivos medidos (Fase 0 / E1). ← bloqueante
- [ ] Elegir plataforma(s): liquidez (Binance) vs profit-share alto + ranking por maxDD (Bybit Pro).
- [ ] Verificar mínimos de lead vigentes y abrir Lead/Master account con capital chico.
- [ ] Validar la **copiabilidad del libro**: nº posiciones × mínimo notional vs ticket típico del seguidor;
      decidir si hace falta variante "lite" o guía de Fixed Ratio.
- [ ] Confirmar settlement + HWM de la plataforma elegida.
- [ ] Reporte de transparencia (F2.1/F2.2) público y honesto: curva, maxDD, Sharpe, β, gap track↔seguidor.
- [ ] Política de profit-share y comunicación: vender bajo-DD/consistencia, NO ROI llamativo.

## Fuentes (2026-06, re-verificar)
- Binance copy trading rules / lead trade / how-to-use FAQ (binance.com/en/support).
- Bybit copy trading profit-sharing + Coin Bureau review (bybit.com/help-center, coinbureau.com).
- Bitget copy trading review + support (bitget.com, coinbureau.com).
- OKX copy trading (tradingfinder.com/exchanges/okx).
