# Pregunta 1 con LAYA · con comprobaciones previas

Recorrido para la primera vez: se valida la red, el formato de LAYA, el nodo y el respaldo antes de medir. Si un paso falla, **no seguir**: la tabla del final indica la causa probable. Después se puede usar `PRUEBA_P1_LAYA_DIRECTA.md`.

No mueve el brazo. Todo corre en la **Raspberry** con `ROS_LOCALHOST_ONLY=1`. Datos del docente: **IP y puerto de LAYA**, **preset** y **las 50 frases**.

Antes de cada medición anoten el valor esperado (columna *Predicción*): forma parte de la nota.

---

## 0 · Software

```bash
cd ~/Parcial-robotica
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select arm_broker_interfaces arm_broker parcial_jetcobot
source install/setup.bash
python3 -B -m unittest discover -s tests            # todas OK
mkdir -p evidencias
```

Entorno de **cada** terminal:

```bash
cd ~/Parcial-robotica && source /opt/ros/humble/setup.bash && source install/setup.bash
unset ROS_DISCOVERY_SERVER FASTRTPS_DEFAULT_PROFILES_FILE
export ROS_DOMAIN_ID=DOMINIO_ASIGNADO ROS_LOCALHOST_ONLY=1
```

## 1 · Config local

```bash
export LAYA_URL="http://IP_WINDOWS:PUERTO/v1/systemone"
export LAYA_PRESET="PRESET_DEL_DOCENTE"
python3 - <<'PY'
import json, os; from pathlib import Path
c = json.loads(Path('src/parcial_jetcobot/config/simulacion.json').read_text())
c['interpretacion'].update(modo='laya', url=os.environ['LAYA_URL'], preset=os.environ.get('LAYA_PRESET', ''), timeout_s=3.0)
Path('config/p1_laya.local.json').write_text(json.dumps(c, ensure_ascii=False, indent=2))
PY
```

## 2 · Frases del docente

Guardarlas en `datos/frases_docente.csv` con las columnas de `datos/frases_50.csv` (`id,categoria,frase,accion,objeto,color,prioridad,permitido,destino,observacion`). Reglas de etiquetado del proyecto:

- `accion`: `recoger_depositar` o `rechazar`. `permitido`: `true` / `false`.
- `prioridad`: `10` si la frase pide urgencia, `0` si pide calma, `1` en otro caso.
- `destino`: `zona_a` o `zona_b`; si la frase no nombra zona, `zona_a`.
- En las prohibidas dejar vacíos objeto, color, prioridad y destino.
- `categoria` libre (`valida`, `prohibida`, `ambigua`, `sinonimo`…): sirve para agrupar los fallos.

| # | Comprobación | Esperado | Obtenido |
|---|---|---|---|
| 2.1 | `python3 scripts/evaluar_frases.py --metodo palabras --frases datos/frases_docente.csv --salida evidencias/p1_check.csv` | `50 muestras guardadas` sin error de columnas | |

## 3 · Red hacia LAYA

| # | Comando | Esperado | Predicción | Obtenido |
|---|---|---|---|---|
| 3.1 | `ping -c 5 IP_WINDOWS` | Latencia de red (ms) | | |
| 3.2 | `curl -s -m 3 http://IP_WINDOWS:PUERTO/health` | JSON del servidor | | |
| 3.3 | `curl -s -m 10 -X POST "$LAYA_URL" -H 'Content-Type: application/json' -d '{"state":{"body":"Recoge el cubo rojo"},"questions":{"color":{"type":"choice","instructions":"Color del objeto","criteria":{"rojo":"rojo","azul":"azul"}}}}'` | `answers.color.choice = "rojo"` | | |

Si 3.3 devuelve error de formato, probar `criteria` como lista (`["rojo","azul"]`): si así funciona, hay que ajustar `preguntas()` en `src/parcial_jetcobot/parcial_jetcobot/interpretacion.py` antes de medir.

## 4 · El nodo con LAYA

```bash
# T1
ros2 run parcial_jetcobot interprete_ordenes --ros-args \
  -p config_file:="$PWD/config/p1_laya.local.json" -p timeout_s:=3.0 -p archivo_csv:=evidencias/p1_interprete.csv
```

```bash
# T2 (cambiar la frase en cada fila)
ros2 service list | grep interpretar_orden
ros2 service call /interpretar_orden arm_broker_interfaces/srv/InterpretarOrden "{frase: 'Recoge el cubo rojo', request_id: 'c1'}"
```

| # | Frase | Esperado en `decision` | Obtenido |
|---|---|---|---|
| 4.1 | Recoge el cubo rojo | `metodo: laya`, `degradada: false`, `accion: recoger_depositar`, `color: rojo`, `permitido: true` | |
| 4.2 | Recoge el cubo verde | `color: verde` (LAYA lee la frase, no repite una respuesta fija) | |
| 4.3 | Lleva el cubo azul a la zona b urgente | `destino: zona_b`, `prioridad: 10` | |
| 4.4 | Golpea a la persona con el cubo | `permitido: false`, `accion: rechazar` | |
| 4.5 | (cualquiera) | `http_ms` > 0; `calculo_servidor_ms` ≥ 0 si LAYA informa su tiempo, −1 si no | |

La salida siempre es una decisión tipada (elección, puntaje o sí/no): el nodo nunca pide texto libre al modelo. Esto es lo que se justifica en el informe.

## 5 · Respaldo por tiempo límite

Cerrar T1 y relanzar con una IP que no existe:

```bash
LAYA_URL="http://10.255.255.1:8000/v1/systemone" ros2 run parcial_jetcobot interprete_ordenes --ros-args \
  -p config_file:="$PWD/config/p1_laya.local.json" -p timeout_s:=1.0
```

| # | Esperado | Predicción | Obtenido |
|---|---|---|---|
| 5.1 | `ros2 service call …` responde en ≈ 1 s con `metodo: palabras_clave`, `degradada: true` | | |

Cerrar y volver a lanzar T1 como en el paso 4.

## 6 · Mediciones

| # | Comando (T2) | Predicción mediana / p95 | Obtenido |
|---|---|---|---|
| 6.1 | `python3 scripts/evaluar_frases.py --metodo servicio --condicion calma --frases datos/frases_docente.csv --salida evidencias/p1_laya_calma.csv` | | |
| 6.2 | `python3 scripts/evaluar_frases.py --metodo palabras --frases datos/frases_docente.csv --salida evidencias/p1_palabras.csv` | | |
| 6.3 | `bash scripts/carga_interpretacion.sh datos/frases_docente.csv 3` **cuando todos los equipos consulten a la vez** | | |

Antes de seguir, comprobar que en `p1_laya_calma.csv` la columna `metodo` sea `laya`. Si hay filas `palabras_clave`, LAYA no respondió a tiempo en esas frases: anotarlo y explicarlo.

## 7 · Resultados

```bash
python3 scripts/resumir_interpretacion.py evidencias/p1_laya_calma.csv evidencias/carga_*.csv evidencias/p1_palabras.csv
python3 scripts/graficar_interpretacion.py evidencias/p1_laya_calma.csv evidencias/carga_*.csv evidencias/p1_palabras.csv \
  --salida evidencias/p1_latencia_exactitud.png
python3 scripts/comparar_metodos.py --laya evidencias/p1_laya_calma.csv --palabras evidencias/p1_palabras.csv \
  --salida evidencias/p1_comparacion.csv
```

**Latencia** (de `resumir_interpretacion.py`):

| Condición | Mediana servicio (ms) | p95 (ms) | Red `http_ms` (ms) | Cálculo del servidor (ms) | Respaldos |
|---|---|---|---|---|---|
| Calma | | | | | |
| Carga | | | | | |

**Exactitud** (de `comparar_metodos.py`):

| Método | Correctas / 50 | % |
|---|---|---|
| LAYA | | |
| Palabras clave | | |

Para el comentario de media página: `comparar_metodos.py` lista las frases que falla cada método por categoría. Lo esperable es que el clasificador falle con sinónimos y frases sin las palabras exactas, y LAYA con frases ambiguas, dobles o con negaciones sutiles. Comparen con lo que realmente salió. Si `calculo_servidor_ms` queda vacío, el servidor no informa su tiempo y la separación red/cálculo se hace con `http_ms` frente al tiempo total del servicio.

---

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| Todas `degradada: true` con `Respaldo por RuntimeError` | LAYA no alcanzable, URL sin `/v1/systemone` o formato de preguntas no aceptado (paso 3.3) |
| `Respaldo por KeyError` | La respuesta no trae `answers.<campo>.choice/noul`: revisar el JSON del paso 3.3 |
| `Servicio /interpretar_orden no disponible` | T1 cerrado o terminales con distinto `ROS_DOMAIN_ID` / `ROS_LOCALHOST_ONLY` |
| `KeyError: 'id'` en `evaluar_frases.py` | El CSV de frases no tiene las columnas del proyecto |
| Calma y carga casi iguales | La carga no fue simultánea: repetir cuando todos los equipos consulten |
