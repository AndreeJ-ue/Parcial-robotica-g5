# ÍTEM 1 — Interpretar la frase (nodo `interprete_ordenes`)

Este documento explica el **Ítem 1** del Parcial JetCobot **a partir de los archivos que se
agregaron para que funcione**: qué pide el enunciado, cómo funciona por dentro, **los comandos
exactos y por qué**, y qué evidencias hay que entregar.

El ítem 1 **no toca el brazo**: solo **entiende la frase** y produce una **decisión tipada**.
Aguas abajo, quien mueve el brazo es el ítem 2 (ver
`PARA_COMPLETAR_EL_ITEM_2_Y_CERRAR_EL_ITEM_3.md`).

---

## 1. Archivos que se agregaron para completar el ítem 1

Estos son los archivos que **no existían** antes de este ítem (el resto —`broker.py`,
`fk.py`, `politicas.py`, las acciones/mensajes del RB-2— ya estaba):

| Archivo (dónde vive) | Qué aporta al ítem 1 |
|---|---|
| `src/arm_broker_interfaces/srv/InterpretarOrden.srv` | **La interfaz**: define el servicio `/interpretar_orden` (petición `frase` + `forzar_clasificador`; respuesta tipada). |
| `src/arm_broker/arm_broker/interprete_ordenes.py` | **El nodo**: expone el servicio, decide entre LAYA y el clasificador y mide tiempos. |
| `src/arm_broker/arm_broker/cliente_laya.py` | **El único módulo que habla HTTP con LAYA**: arma la consulta tipada y lee la respuesta. |
| `src/arm_broker/arm_broker/clasificador_palabras_clave.py` | **El respaldo local** sin red ni IA (regla determinística). |
| `herramientas/probar_laya.py` | Prueba LAYA **sin ROS 2** (ver la respuesta cruda). |
| `herramientas/medir_item1.py` | Mide **latencia y exactitud** sobre las 50 frases. |
| `herramientas/frases_ejemplo.csv` | 8 frases de ejemplo para una prueba rápida. |
| `evidencias/frases_50.csv` | Plantilla de las 50 frases del docente (con columnas `esperado_*`). |

> **Nota sobre el código:** los módulos de este ítem están **reescritos/parafraseados** (nombres
> internos, comentarios y docstrings propios) pero **conservan intacto el contrato de conexión**:
> el nombre del servicio `/interpretar_orden`, los campos del `.srv`, los nombres de los
> parámetros, la variable de entorno `LAYA_API_KEY` y los endpoints HTTP de LAYA. Por eso sigue
> funcionando igual con el broker y con las herramientas.

---

## 2. Qué pide el enunciado

1. Un nodo ROS 2 **`interprete_ordenes`** con servicio **`/interpretar_orden`** que reciba una
   frase y devuelva al menos **acción, objeto, color, prioridad (entero) y permitido (bool)**,
   consultando internamente a **LAYA**.
2. **Nada de texto libre**: la salida de LAYA debe ser una **decisión tipada** (elegir una opción,
   un puntaje o un sí/no) y hay que justificar por qué eso importa en un robot.
3. **Tiempo límite como parámetro del nodo**: si LAYA no contesta a tiempo → **clasificador propio
   por palabras clave** + bandera **`degradada`**. El sistema **nunca** se queda esperando.
4. Medir **latencia** sobre las **50 frases** del docente: **mediana y p95**, separando **red** de
   **cómputo**.
5. Repetir la medición **en calma** y **con todos los equipos cargando**.
6. Tabla comparativa de **exactitud**: LAYA vs clasificador.
7. **Entregables**: código, CSV con las 50 frases y la decisión de cada método, tablas de latencia
   (calma/carga) y exactitud, y media página de comentario.

---

## 3. Cómo funciona (el flujo)

```
frase ──► interprete_ordenes.atender()
             │  ¿forzar_clasificador?
             ├─ no ─► cliente_laya.preguntar()  ──HTTP──► LAYA (/v1/systemone)
             │          │ se cumple timeout_laya_s            (tu PC, GPU)
             │          ▼
             │        respuesta tipada → degradada=False, fuente='laya'
             │          tiempo_red    = línea base medida en /health al arrancar
             │          tiempo_computo = total − red
             │
             └─ sí / error / timeout ─► clasificador.clasificar()
                        ▼
                      mismo dict → degradada=True, fuente='palabras_clave'
```

Qué hace cada archivo (con los nombres internos ya parafraseados):

| Archivo | Qué hace |
|---|---|
| `InterpretarOrden.srv` | Interfaz del servicio. Petición: `frase` + `forzar_clasificador`. Respuesta: `accion, objeto, color, prioridad, permitido, motivo, degradada, fuente, tiempo_total_s, tiempo_red_s, tiempo_computo_s`. |
| `interprete_ordenes.py` | El nodo. Parámetros `laya_url` (default `http://127.0.0.1:8000`), `timeout_laya_s` (2.0), `objetos`, `colores`, `acciones`. Mide la **línea base de red** contra `/health` al arrancar y crea el servicio. |
| `cliente_laya.py` | **Único** módulo HTTP. Arma 5 preguntas tipadas (`choice` para acción/objeto/color, `score` para prioridad, `noul` para permitido) y hace `POST {url}/v1/systemone`. Incluye `medir_red_base()` (5× `GET /health`, mediana). |
| `clasificador_palabras_clave.py` | Plan B sin red ni IA: diccionarios de sinónimos (`VERBOS`, `FORMAS`, `TONOS`) + lista de palabras vetadas (`VETADAS`). Devuelve el **mismo dict**. `permitido=False` si hay palabra vetada o acción desconocida. **Prioridad siempre 1**. |

---

## 4. Comandos exactos (y por qué)

### Paso A — En la PC Windows: instalar y levantar LAYA

LAYA es **self-hosted**: se instala y corre en tu PC, no es una API en la nube. Solo la primera
vez usa internet para descargar el modelo.

```powershell
# A.1) Crear entorno virtual
mkdir C:\laya ; cd C:\laya
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1          # si falla: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# A.2) Instalar PyTorch con CUDA y LAYA con servidor
python -m pip install -U pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cu121
python -m pip install "laya[serve]"   # agrega el comando laya-serve

# A.3) Levantar el servidor
$env:LAYA_HOST    = "0.0.0.0"         # escucha en toda la LAN (no solo localhost)
$env:LAYA_PORT    = "8000"
$env:LAYA_DEVICE  = "cuda"            # o "cpu" si falla la GPU
$env:LAYA_MODELS  = "multilingual"    # un checkpoint (español), cabe en 4 GB
$env:LAYA_PRELOAD = "1"
# opcional: $env:LAYA_API_KEY = "una-clave-larga-que-inventes"
laya-serve
```

**Por qué `LAYA_HOST=0.0.0.0`** y no `127.0.0.1`: la Jetson tiene que poder llegar a tu PC por la
red local.

### Paso B — Confirmar que LAYA contesta (sin ROS 2)

**Por qué:** el formato exacto del JSON solo se confirma contra el servidor real. Se corre
**primero**, antes de confiar en el nodo.

```powershell
# Desde tu PC:
curl.exe -s http://127.0.0.1:8000/health                  # debe dar status=200
python herramientas\probar_laya.py http://127.0.0.1:8000 "agarra el cubo rojo"
```

Revisa que existan los campos `answers.accion.choice`, `answers.prioridad.score`,
`answers.permitido.noul`. Si el JSON real usa otros nombres (`label`, `value`, `answer`...), se
ajusta la lista dentro de `_campo()` en `cliente_laya.py`.

```bash
# Desde la Jetson (así se usará el día del examen):
curl -s http://<IP_DE_TU_PC>:8000/health
python3 herramientas/probar_laya.py http://<IP_DE_TU_PC>:8000 "agarra el cubo rojo"
```

### Paso C — En la Jetson: entorno, compilar y arrancar

```bash
# C.1) Entorno ROS (IGUAL en todas las máquinas)
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=43                        # 42 + nº de equipo
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DISCOVERY_SERVER="172.51.1.28:11811"
ros2 daemon stop; ros2 daemon start

# C.2) Dependencia del cliente HTTP (si no la tiene)
pip3 install requests --break-system-packages

# C.3) Compilar los dos paquetes juntos y activar
cd ~/rb2_ws
colcon build --packages-select arm_broker_interfaces arm_broker --symlink-install
source install/setup.bash
```

```bash
# C.4) Arrancar el nodo apuntando a tu PC
export LAYA_API_KEY="misma-clave-que-en-el-servidor"   # solo si pusiste clave (lo normal es no usarla aquí)
ros2 run arm_broker interprete_ordenes --ros-args \
  -p laya_url:=http://<IP_DE_TU_PC>:8000 \
  -p timeout_laya_s:=2.0 \
  -p objetos:="['cubo','cilindro','esfera']" \
  -p colores:="['rojo','verde','azul','amarillo']" \
  -p acciones:="['agarrar','soltar','mover','detener']"
```

**Por qué `-p laya_url`:** el default es `127.0.0.1:8000` (solo sirve si LAYA corriera en la misma
máquina). Desde la Jetson hay que darle la IP real de tu PC.

### Paso D — Probar el servicio a mano

```bash
# Normal (irá a LAYA)
ros2 service call /interpretar_orden arm_broker_interfaces/srv/InterpretarOrden \
  "{frase: 'agarra el cubo rojo'}"

# Forzando el clasificador local (sin tocar LAYA) — así se mide el respaldo por separado
ros2 service call /interpretar_orden arm_broker_interfaces/srv/InterpretarOrden \
  "{frase: 'agarra el cubo rojo', forzar_clasificador: true}"
```

Log esperado en la terminal del nodo:

```
✅ [LAYA] "agarra el cubo rojo" → agarrar/cubo/rojo p=1 permitido=True · 420 ms
```

### Paso E — Demostrar la degradación (sin LAYA)

Apaga `laya-serve` (o apunta a una IP muerta) y vuelve a llamar. A los 2 s responde el
clasificador:

```
⚠️  [DEGRADADA] "agarra el cubo rojo" → agarrar/cubo/rojo p=1 permitido=True · 2003 ms
```

**Por qué importa:** es la evidencia de que **el sistema nunca se queda esperando**.

### Paso F — Medir latencia y exactitud

```bash
# F.1) Validación rápida con las 8 frases de ejemplo
python3 herramientas/medir_item1.py herramientas/frases_ejemplo.csv salida_prueba.csv

# F.2) ANTES de medir, anota tu predicción (regla del examen), p. ej.:
#      "mediana ≈ 300 ms, p95 ≈ 900 ms en calma; bajo carga la mediana se duplica"

# F.3) Con las 50 frases oficiales (frases_50.csv)
python3 herramientas/medir_item1.py frases_50.csv resultados_calma.csv
python3 herramientas/medir_item1.py frases_50.csv resultados_carga.csv   # con los 4 equipos preguntando
```

`medir_item1.py` hace **dos** llamadas por frase (normal y `forzar_clasificador=True`) e imprime
**mediana y p95** de total/red/cómputo y la tabla de **exactitud** (si el CSV trae columnas
`esperado_*`).

---

## 5. Avisos / problemas comunes

- **Falta `requests`** → `pip3 install requests --break-system-packages`.
- **La Jetson no conecta con LAYA** → firewall TCP 8000 abierto y `LAYA_HOST=0.0.0.0` (no `127.0.0.1`).
- **Resumen LAYA vacío** → todas las respuestas fueron degradadas (LAYA no respondió): revisa la red.
- **Prioridad del clasificador siempre 1** → no estima urgencia; úsalo en el informe de exactitud.
- **`colcon build` no encuentra `InterpretarOrden`** → revisa que el `.srv` tenga el separador `---`
  y que `"srv/InterpretarOrden.srv"` esté en `rosidl_generate_interfaces(...)` del `CMakeLists.txt`.
- **Sinónimos no listados** → el clasificador falla (busca por substring en listas fijas).
- **Privacidad** → la clave de LAYA solo por variable de entorno, nunca en el código.

Ver `EVIDENCIAS_ITEM_1.md` para los entregables y el checklist.
