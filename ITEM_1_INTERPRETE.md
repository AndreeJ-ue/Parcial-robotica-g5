# ÍTEM 1 — Interpretar la frase (nodo `interprete_ordenes`)

El ítem 1 **no mueve el brazo**: recibe una **frase** ("agarra el cubo rojo") y devuelve una
**decisión tipada** (acción, objeto, color, prioridad, permitido). Consulta a **LAYA** por HTTP y,
si no responde a tiempo, cae a un **clasificador por palabras clave** (`degradada=True`).
Aguas abajo, quien mueve el brazo es el ítem 2 (`ITEM_2_BRAZO.md`).

---

## 1. Qué pide el enunciado

1. Nodo ROS 2 **`interprete_ordenes`** con servicio **`/interpretar_orden`** que reciba una frase y
   devuelva al menos **acción, objeto, color, prioridad (entero) y permitido (bool)**, consultando
   internamente a **LAYA**.
2. **Nada de texto libre**: la salida de LAYA debe ser una **decisión tipada** (elegir una opción,
   un puntaje o un sí/no).
3. **Tiempo límite como parámetro del nodo**: si LAYA no contesta a tiempo → **clasificador propio
   por palabras clave** + bandera **`degradada`**. El sistema **nunca** se queda esperando.
4. Medir **latencia** sobre las **50 frases** del docente: **mediana y p95**, separando **red** de
   **cómputo**.
5. Repetir la medición **en calma** y **con todos los equipos cargando**.
6. Tabla comparativa de **exactitud**: LAYA vs clasificador.
7. **Entregables**: código, CSV con las 50 frases y la decisión de cada método, tablas de latencia
   (calma/carga) y exactitud, y media página de comentario.

## 2. Archivos del ítem 1

| Archivo | Qué aporta |
|---|---|
| `src/arm_broker_interfaces/srv/InterpretarOrden.srv` | La interfaz: servicio `/interpretar_orden` (petición `frase` + `forzar_clasificador`; respuesta tipada). |
| `src/arm_broker/arm_broker/interprete_ordenes.py` | El nodo: expone el servicio, decide entre LAYA y el clasificador y mide tiempos. |
| `src/arm_broker/arm_broker/cliente_laya.py` | Único módulo HTTP con LAYA: arma las preguntas tipadas y lee la respuesta. |
| `src/arm_broker/arm_broker/clasificador_palabras_clave.py` | Respaldo local sin red ni IA (prioridad siempre 1). |
| `herramientas/probar_laya.py` | Prueba LAYA **sin ROS 2**. |
| `herramientas/medir_item1.py` | Mide **latencia y exactitud** sobre las 50 frases. |
| `herramientas/frases_ejemplo.csv` | 8 frases de ejemplo para prueba rápida. |
| `evidencias/frases_50.csv` | Plantilla de las 50 frases (con columnas `esperado_*`). |

## 3. Cómo funciona

```
frase ──► interprete_ordenes.atender()
             │  ¿forzar_clasificador?
             ├─ no ─► cliente_laya.preguntar()  ──HTTP──► LAYA (PC, /v1/systemone)
             │          │ se cumple timeout_laya_s
             │          ▼
             │        respuesta tipada → degradada=False, fuente='laya'
             │          tiempo_red     = línea base medida en /health al arrancar
             │          tiempo_computo = total − red
             │
             └─ sí / error / timeout ─► clasificador.clasificar()
                        ▼
                      mismo dict → degradada=True, fuente='palabras_clave'
```

- `cliente_laya.py` arma 5 preguntas tipadas (`choice` para acción/objeto/color, `score` para
  prioridad, `noul` para permitido) y hace `POST {url}/v1/systemone`.
- `clasificador_palabras_clave.py` usa diccionarios de sinónimos + palabras vetadas. Devuelve
  `permitido=False` si hay palabra vetada o acción desconocida.

---

## 4. Comandos exactos, paso a paso

### Entorno (en CADA terminal de la Jetson)
```bash
cd ~/rb2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=47                     # el que asigne el docente (42 + nº de equipo)
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DISCOVERY_SERVER="<IP_DEL_ROBOT>:11811"
ros2 daemon stop; ros2 daemon start
```

### Paso A — En la PC Windows: levantar LAYA
LAYA es **self-hosted** (corre en tu PC, no en la nube). Solo la primera vez usa internet.

```powershell
mkdir C:\laya ; cd C:\laya
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1      # si falla: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

python -m pip install -U pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cu121
python -m pip install "laya[serve]"

$env:LAYA_HOST    = "0.0.0.0"      # escucha en toda la LAN (no solo localhost)
$env:LAYA_PORT    = "8000"
$env:LAYA_DEVICE  = "cuda"         # o "cpu"
$env:LAYA_MODELS  = "multilingual"
$env:LAYA_PRELOAD = "1"
laya-serve
```
**Por qué `LAYA_HOST=0.0.0.0`:** la Jetson tiene que llegar a tu PC por la red local.

### Paso B — Confirmar que LAYA contesta (sin ROS 2)
```powershell
# Desde la PC:
curl.exe -s http://127.0.0.1:8000/health
python herramientas\probar_laya.py http://127.0.0.1:8000 "agarra el cubo rojo"
```
```bash
# Desde la Jetson (así se usará el día del examen):
curl -s http://<IP_DE_TU_PC>:8000/health
python3 herramientas/probar_laya.py http://<IP_DE_TU_PC>:8000 "agarra el cubo rojo"
```
Revisa que existan los campos `answers.accion.choice`, `answers.prioridad.score`,
`answers.permitido.noul`. Si el JSON real usa otros nombres, se ajusta en `_campo()` de
`cliente_laya.py`.

### Paso C — Compilar y arrancar el nodo (Jetson)
```bash
pip3 install requests --break-system-packages      # si falta
cd ~/rb2_ws
colcon build --packages-select arm_broker_interfaces arm_broker --symlink-install
source install/setup.bash

export LAYA_API_KEY="misma-clave-que-en-el-servidor"   # solo si pusiste clave
ros2 run arm_broker interprete_ordenes --ros-args \
  -p laya_url:=http://<IP_DE_TU_PC>:8000 \
  -p timeout_laya_s:=2.0 \
  -p objetos:="['cubo','cilindro','esfera']" \
  -p colores:="['rojo','verde','azul','amarillo']" \
  -p acciones:="['agarrar','soltar','mover','detener']"
```
**Por qué `-p laya_url`:** el default es `127.0.0.1:8000` (solo válido si LAYA corriera en la misma
máquina). Desde la Jetson hay que darle la IP real de tu PC.

### Paso D — Probar el servicio a mano
```bash
# Normal (va a LAYA)
ros2 service call /interpretar_orden arm_broker_interfaces/srv/InterpretarOrden \
  "{frase: 'agarra el cubo rojo'}"

# Forzando el clasificador local (sin tocar LAYA)
ros2 service call /interpretar_orden arm_broker_interfaces/srv/InterpretarOrden \
  "{frase: 'agarra el cubo rojo', forzar_clasificador: true}"
```
Log esperado:
```
✅ [LAYA] "agarra el cubo rojo" → agarrar/cubo/rojo p=1 permitido=True · 420 ms
```

### Paso E — Demostrar la degradación (sin LAYA)
Apaga `laya-serve` (o apunta a una IP muerta) y vuelve a llamar. A los 2 s responde el clasificador:
```
⚠️  [DEGRADADA] "agarra el cubo rojo" → agarrar/cubo/rojo p=1 permitido=True · 2003 ms
```
Evidencia de que **el sistema nunca se queda esperando**.

### Paso F — Medir latencia y exactitud
```bash
# Validación rápida con las 8 frases de ejemplo
python3 herramientas/medir_item1.py herramientas/frases_ejemplo.csv salida_prueba.csv

# Con las 50 frases oficiales (medir en calma y bajo carga)
python3 herramientas/medir_item1.py evidencias/frases_50.csv resultados_calma.csv
python3 herramientas/medir_item1.py evidencias/frases_50.csv resultados_carga.csv
```
`medir_item1.py` hace dos llamadas por frase (normal y `forzar_clasificador=True`) e imprime
**mediana y p95** de total/red/cómputo y la tabla de **exactitud**.

> Anota tu **predicción previa** antes de medir (regla del examen): p. ej. "mediana ≈ 300 ms,
> p95 ≈ 900 ms en calma; bajo carga la mediana se duplica".

---

## 5. Verificación y evidencias

| Evidencia | Cómo se genera |
|---|---|
| `frases_50.csv` | Plantilla en `evidencias/frases_50.csv`. |
| `evidencia/laya_prueba.txt` | `python herramientas/probar_laya.py http://<IP>:8000 "agarra el cubo rojo"` (PC). |
| `evidencia/servicio_interpretar.txt` | `ros2 service call /interpretar_orden ...` (normal **y** con `forzar_clasificador: true`). |
| `resultados_calma.csv` / `resultados_carga.csv` | `medir_item1.py` (calma y con los 4 equipos cargando). |
| `evidencia/resumen_calma.txt` / `resumen_carga.txt` | Salida de cada corrida (`... | tee ...`). |
| Tablas de latencia + exactitud y media página de comentario | Se arman con los resúmenes. |

**Checklist:**
- [ ] `interprete_ordenes` responde por `/interpretar_orden`.
- [ ] La degradación al clasificador funciona (apagar LAYA y repetir).
- [ ] `resultados_calma.csv` y `resultados_carga.csv`.
- [ ] `evidencia/resumen_calma.txt` y `resumen_carga.txt`.
- [ ] `evidencia/laya_prueba.txt` y `servicio_interpretar.txt`.
- [ ] Tablas de latencia (calma/carga) y de exactitud.
- [ ] Media página de comentario.

**Comentario (qué escribir):** compara en el CSV las filas `acierto_laya=False` vs
`acierto_clasificador=False`:
- **Clasificador**: falla con **sinónimos no listados** ("agarrame el cubito"), frases sin acción
  clara; prioridad siempre 1.
- **LAYA**: falla con frases **vagas o con doble acción** ("agarra el cubo y déjalo azul") y puede
  marcar mal `permitido`.
- Si hubo `DEGRADADAS`, explica **por qué** (timeout o servidor saturado).

## 6. Problemas comunes
- **Falta `requests`** → `pip3 install requests --break-system-packages`.
- **La Jetson no conecta con LAYA** → firewall TCP 8000 abierto y `LAYA_HOST=0.0.0.0`.
- **Resumen LAYA vacío** → todas las respuestas fueron degradadas (revisa la red).
- **`colcon build` no encuentra `InterpretarOrden`** → revisa el separador `---` del `.srv` y que
  esté en `rosidl_generate_interfaces(...)`.
- **Privacidad** → la clave de LAYA solo por variable de entorno.
