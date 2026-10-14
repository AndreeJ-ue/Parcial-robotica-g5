#!/usr/bin/env bash
set -euo pipefail
raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"
mkdir -p evidencias
pids=()
for n in 1 2 3 4; do
  ros2 run parcial_jetcobot cliente_ordenes --ros-args -p client_id:="integrante_$n" \
    -p archivo_ordenes:="$raiz/datos/cliente_$n.txt" \
    -p archivo_resultados:="$raiz/evidencias/cliente_$n.jsonl" >"evidencias/cliente_$n.log" 2>&1 &
  pids+=("$!")
done
estado=0
for pid in "${pids[@]}"; do wait "$pid" || estado=1; done
exit "$estado"
