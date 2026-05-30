# Kepler

Sistema cuantitativo **multi-activo** para cripto (Binance), hijo de Sentinel.
Market-neutral por defecto, combina edges no correlacionados, dirigido por evidencia.

- **Misión y principios:** `INSTRUCTIONS.md`
- **Plan maestro:** `PLAN.md`

## Estructura
```
config.py              universo, rutas, supuestos de costo/riesgo
kepler/
  fetch.py             descargador multi-activo (data.binance.vision) — reanudable
  db.py                SQLite: signals, trades, portfolio, equity, daily_report, audit
research/
  e1_dominance.py      E1 — estudio lead-lag / dominancia (¿quién dirige a quién?)
data/                  parquet store (futures_um/<interval>, spot, funding)
logs/                  reportes/logs diarios descargables
```

## Uso
```
pip install -r requirements.txt
python -m kepler.fetch 1h           # universo en 1h (estudios)
python -m kepler.db                 # inicializa la DB
python research/e1_dominance.py     # estudio de dominancia
```

## Estado (2026-05-29)
Fundamentos en marcha: datos (E0), DB/auditoría, estudio E1. Ver `PLAN.md` §7 para etapas.
Workflow: propuesta → backtest → implementar solo si mejora rentabilidad Y riesgo.
