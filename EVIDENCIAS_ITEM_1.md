# Evidencias — ÍTEM 1

## Tabla de entregables (y con qué comando se generan)

| Evidencia | Cómo se genera |
|---|---|
| `frases_50.csv` | Plantilla en `anchy/evidencias/frases_50.csv` (con columnas `esperado_*`). |
| `evidencia/laya_prueba.txt` | `python herramientas/probar_laya.py http://<IP>:8000 "agarra el cubo rojo"` (en la PC; guarda la salida). |
| `evidencia/servicio_interpretar.txt` | `ros2 service call /interpretar_orden ...` (normal **y** con `forzar_clasificador: true`). |
| `resultados_calma.csv` | `python3 herramientas/medir_item1.py frases_50.csv resultados_calma.csv` |
| `resultados_carga.csv` | Igual, pero mientras los 4 equipos cargan a la vez. |
| `evidencia/resumen_calma.txt` | Salida de la corrida en calma (`... | tee evidencia/resumen_calma.txt`). |
| `evidencia/resumen_carga.txt` | Salida de la corrida bajo carga. |
| Tablas de latencia (calma/carga) + exactitud | Se arman con los resúmenes. |
| Media página de comentario | Ver abajo. |

## Qué te imprime `medir_item1.py`

- Por frase: resultado de LAYA y del clasificador, marcando `⚠️ DEGRADADA` cuando LAYA no
  contestó a tiempo.
- Resumen: **mediana y p95** de `total`, `red (aprox.)`, `cómputo (aprox.)`.
- Tabla de **exactitud** LAYA vs clasificador (solo si el CSV trae `esperado_*`).
- CSV fila por fila con todo (esa es la evidencia que se entrega).

## Checklist de entrega (ítem 1)

- [ ] `interprete_ordenes` responde por `/interpretar_orden`.
- [ ] La degradación al clasificador funciona (apagar LAYA y repetir).
- [ ] `resultados_calma.csv` y `resultados_carga.csv`.
- [ ] `evidencia/resumen_calma.txt` y `resumen_carga.txt`.
- [ ] `evidencia/laya_prueba.txt` y `servicio_interpretar.txt`.
- [ ] Tablas de latencia (calma/carga) y de exactitud.
- [ ] Media página de comentario.

## Media página de comentario (qué escribir)

Compara en el CSV las filas `acierto_laya=False` vs `acierto_clasificador=False` y explica
**qué frases falla cada método**:

- **Clasificador**: falla con **sinónimos no listados** ("agarrame el cubito", "recoge la
  bolita"), frases sin acción clara, y manda **prioridad siempre 1**.
- **LAYA**: falla con frases **vagas o con doble acción** ("agarra el cubo y déjalo azul") y
  puede marcar mal `permitido` en órdenes raras.
- Si hubo `DEGRADADAS`, explica **por qué** (timeout o servidor saturado).

## Predicción previa (anótala ANTES de medir)

Ejemplo: *"esperamos mediana ≈ 300 ms y p95 ≈ 900 ms en calma; bajo carga la mediana se
duplica; LAYA ≥ 85 % de exactitud, clasificador ≈ 70 %"*. Ajusta a lo que creas y luego
compáralo con lo medido.
