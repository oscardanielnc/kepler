# E13b — Análisis copy-trader "Flowerence29" (2026-05-30)

Hermano del análisis E13 (Btc-Panda). Oscar evaluó copiar a este "Maestro" por sus números.
**Veredicto: NO copiar. Mismo martingala que Brayan, mejor disfrazado.**

## Datos del perfil (capturas de Oscar)
- ROI: 7d +36.8% · 30d +184.55% · 90d +172.02%
- MDD reportado: 0.03% / 0.13% / 0.09%
- Sharpe: **5.11 idéntico en los 3 periodos**
- AUM gestionado **607.863 USDT** vs margen propio del trader **15.709 USDT**
- Profit sharing 12% · 52 días de trading · etiqueta "Apalancamiento alto", "Trading vía API"
- Activos preferidos 7d: **ZEC 99.348%**

## Banderas rojas (todas de sus propios datos)
1. **MDD ~0% con +184%/mes es imposible** → métrica rota/manipulada, no skill.
2. **Esconde el DD manteniendo perdedores ABIERTOS:** `SUIUSDT` Long `closed:null` roi −24%;
   `DOGEUSDT` Long `closed:null`. El MDD se mide sobre PnL CERRADO → la pérdida latente nunca
   "se realiza". Truco clásico de martingala en cross margin.
3. **99% de la ganancia semanal = 1 trade:** PnL 7d +5.709,88; trade ZEC (id 1779966247187)
   +5.659,27 → **99.1%**. Concentración 99.3% en ZEC. No es consistencia, es una apuesta.
4. **~19-20x de leverage:** ZEC 524.95→536.28 = +2.16% de precio → ROI +41.67%. Leverage "20" en
   el historial. Un −2% en contra con 20x ≈ −40% de cuenta.
5. **Sharpe 5.11 clavado en 7d/30d/90d** = artefacto del panel. Si eso está roto, el MDD del mismo
   panel tampoco es confiable.
6. **Poca piel en el juego:** gana por volumen de copiadores + 12% profit-share. Si revienta, el
   copiador pierde capital; el trader pierde 15k y reabre. 52 días = no ha vivido un mal periodo.

## Cómo lo hace (una frase)
20x sobre alts en racha (sobre todo ZEC, que tuvo un rally), **aguantando los perdedores abiertos**
para que el drawdown realizado se vea en ~0%. Espectacular hasta que la moneda revierte o lo liquidan.

## Comparación con Kepler
| | Flowerence29 | Kepler |
|---|---|---|
| MDD | oculto (perdedores abiertos, 20x) | −11.6% medido, honesto |
| Retorno | +184%/mes (1 trade ZEC) | +1.2%/mes (5 sleeves, β≈0) |
| Sharpe | 5.11 (idéntico = roto) | 1.13 (auditado) |
| Concentración | 99% ZEC | ~16 posiciones |
| Sobrevive un crash | No | Diseñado para sí |

Conclusión: copiarlo = cambiar a Brayan por otro Brayan. Kepler es el opuesto (copy-lead honesto).
