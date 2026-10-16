#!/usr/bin/env bash
# Cuatro procesos consultan solo interpretación: no envía acciones al robot.
set -euo pipefail
raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"
pids=()
for n in 1 2 3 4; do
  python3 scripts/evaluar_frases.py --metodo servicio --condicion carga --repeticiones 3 \
    --salida "evidencias/carga_$n.csv" &
  pids+=("$!")
done
estado=0
for pid in "${pids[@]}"; do wait "$pid" || estado=1; done
exit "$estado"
