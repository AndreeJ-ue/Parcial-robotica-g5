#!/usr/bin/env bash
# Cuatro procesos consultan solo interpretación: no envía acciones al robot.
# Uso: bash scripts/carga_interpretacion.sh [frases.csv] [repeticiones]
set -euo pipefail
raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"
frases="${1:-datos/frases_50.csv}"
repeticiones="${2:-3}"
mkdir -p evidencias
pids=()
for n in 1 2 3 4; do
  python3 scripts/evaluar_frases.py --metodo servicio --condicion carga --repeticiones "$repeticiones" \
    --frases "$frases" --salida "evidencias/carga_$n.csv" &
  pids+=("$!")
done
estado=0
for pid in "${pids[@]}"; do wait "$pid" || estado=1; done
exit "$estado"
