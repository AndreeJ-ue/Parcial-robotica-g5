# ÍTEM 1 — Interpretar la frase → decisión tipada (nodo `interprete_ordenes`)

El **ítem 1 no mueve el brazo**: recibe una **frase** ("agarra el cubo rojo") y devuelve una
**decisión tipada** (acción, objeto, color, prioridad, permitido). Consulta a **LAYA** por HTTP y, si
no responde a tiempo, cae a un **clasificador por palabras clave** con la bandera `degradada=True`.
El movimiento del brazo es el ítem 2 (`ITEM_2_BRAZO.md`).

> **Idea clave:** el modelo **nunca** devuelve texto libre. La salida es una **opción de un catálogo
> cerrado** (`choice`), un **puntaje** (`score`) o un **sí/no** (`noul`). Así una respuesta rara no
> puede mover el brazo a cualquier lado.

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
7. **Entregables**: código · CSV con las 50 frases y la decisión de cada método · tablas de latencia
   (calma/carga) y exactitud · media página de comentario.

## 2. Arquitectura / flujo

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
                        │
                        ▼
             /interpretar_orden (respuesta)  ─►  y por tópico, la decisión queda lista para el ítem 2
```

**Cómo se comporta cada pieza**

- `cliente_laya.py` es el **único** módulo HTTP con LAYA: arma 5 preguntas tipadas (`choice` para
  acción/objeto/color, `score` para prioridad, `noul` para permitido) y hace `POST {url}/v1/systemone`.
  Su `permitido` es **fail-safe** (`False` por defecto) y **descarta** cualquier valor fuera del
  catálogo cerrado.
- `validez.py` reaplica las reglas duras **al resultado, venga de donde venga**: una frase con
  palabra vetada queda `permitido=False` aunque LAYA diga que sí, y una acción fuera de la lista
  cerrada (`agarrar/soltar/mover/detener`) también. Si LAYA no reconoce la acción, el intérprete
  **cae al clasificador local** en vez de propagar una decisión inservible.
- `clasificador_palabras_clave.py` usa diccionarios de sinónimos + palabras vetadas (sin red ni IA);
  devuelve `permitido=False` si hay palabra vetada o acción desconocida, y **prioridad siempre 1**.

## 3. Archivos del ítem 1

| Archivo | Qué aporta |
|---|---|
| `src/arm_broker_interfaces/srv/InterpretarOrden.srv` | La interfaz: servicio `/interpretar_orden` (petición `frase` + `forzar_clasificador`; respuesta tipada). |
| `src/arm_broker/arm_broker/interprete_ordenes.py` | El nodo: expone el servicio, decide entre LAYA y el clasificador y mide tiempos. |
| `src/arm_broker/arm_broker/cliente_laya.py` | Único módulo HTTP con LAYA: arma las preguntas tipadas y lee la respuesta. |
| `src/arm_broker/arm_broker/validez.py` | Reglas duras compartidas: acción válida + palabras vetadas (se aplican a LAYA y al clasificador). |
| `src/arm_broker/arm_broker/clasificador_palabras_clave.py` | Respaldo local sin red ni IA. |
| `herramientas/probar_laya.py` | Prueba LAYA **sin ROS 2**. |
| `herramientas/medir_item1.py` | Mide **latencia y exactitud** sobre las 50 frases. |
| `herramientas/frases_ejemplo.csv` | 8 frases de ejemplo para prueba rápida. |
| `evidencias/frases_50.csv` | Plantilla de las 50 frases (con columnas `esperado_*`). |

Entry point en `setup.py`: `interprete_ordenes`.

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
**Qué hace:** entra al workspace, carga ROS 2 Humble y el paquete compilado, fija el dominio DDS (para
no cruzarse con otros equipos), el middleware FastRTPS y el servidor de descubrimiento, y reinicia el
daemon de ROS para que vea los nodos recién arrancados.

### Paso A — En la PC Windows: levantar LAYA
LAYA es **self-hosted** (corre en tu PC, no en la nube). Solo la primera vez usa internet para bajar
el modelo.

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
**Qué hace:** crea un entorno virtual, instala LAYA con Torch (GPU `cu121`; usa `cpu` si no hay GPU) y
arranca el servidor. **Por qué `LAYA_HOST=0.0.0.0`:** la Jetson tiene que llegar a tu PC por la red
local; con `127.0.0.1` solo escucharía a sí misma.

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
**Qué hace:** comprueba que LAYA está vivo y hace **una** pregunta tipada, sin ROS 2, para ver la
forma real del JSON. Revisa que existan los campos `answers.accion.choice`, `answers.prioridad.score`
y `answers.permitido.noul`; si el JSON real usa otros nombres se ajusta en `_campo()` de
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
**Qué hace:** compila sólo los dos paquetes del proyecto (rápido, no recompila todo el workspace) y
arranca el nodo con su **catálogo cerrado** de objetos/colores/acciones. **Por qué `-p laya_url`:** el
default es `127.0.0.1:8000` (solo válido si LAYA corriera en la misma máquina); desde la Jetson hay
que darle la **IP real de tu PC**. **Por qué `timeout_laya_s=2.0`:** es el límite a partir del cual
salta el clasificador (punto 3 del enunciado).

### Paso D — Probar el servicio a mano
```bash
# Normal (va a LAYA)
ros2 service call /interpretar_orden arm_broker_interfaces/srv/InterpretarOrden \
  "{frase: 'agarra el cubo rojo'}"

# Forzando el clasificador local (sin tocar LAYA)
ros2 service call /interpretar_orden arm_broker_interfaces/srv/InterpretarOrden \
  "{frase: 'agarra el cubo rojo', forzar_clasificador: true}"
```
**Qué hace:** invoca el servicio directamente y muestra la decisión tipada. El segundo comando usa
`forzar_clasificador:=true` para probar el respaldo sin depender de LAYA. Log esperado:
```
✅ [LAYA] "agarra el cubo rojo" → agarrar/cubo/rojo p=1 permitido=True · 420 ms
```

### Paso E — Demostrar la degradación (sin LAYA)
Apaga `laya-serve` (o apunta `-p laya_url` a una IP muerta) y vuelve a llamar.
**Qué hace:** demuestra que a los 2 s (`timeout_laya_s`) responde el **clasificador** y **no** se
queda esperando:
```
⚠️  [DEGRADADA] "agarra el cubo rojo" → agarrar/cubo/rojo p=1 permitido=True · 2003 ms
```

### Paso F — Medir latencia y exactitud
```bash
# Validación rápida con las 8 frases de ejemplo
python3 herramientas/medir_item1.py herramientas/frases_ejemplo.csv salida_prueba.csv

# Con las 50 frases oficiales (medir en calma y bajo carga)
python3 herramientas/medir_item1.py evidencias/frases_50.csv resultados_calma.csv
python3 herramientas/medir_item1.py evidencias/frases_50.csv resultados_carga.csv
```
**Qué hace:** por cada frase hace **dos** llamadas (normal contra LAYA y `forzar_clasificador=True`) e
imprime **mediana y p95** de total/red/cómputo y la tabla de **exactitud**. El CSV guarda la decisión
de cada método para comparar.

> **Regla del examen:** anota tu **predicción previa** antes de medir (p. ej. "mediana ≈ 300 ms,
> p95 ≈ 900 ms en calma; bajo carga la mediana se duplica").

---

## 5. Parámetros del nodo (`interprete_ordenes`)

| Parámetro | Ejemplo | Qué significa |
|---|---|---|
| `laya_url` | `http://<IP_PC>:8000` | Dirección de LAYA. Default `127.0.0.1:8000`. |
| `timeout_laya_s` | `2.0` | Espera máxima a LAYA; al vencer salta el clasificador (`degradada`). |
| `objetos` | `['cubo','cilindro','esfera']` | Catálogo cerrado de objetos. |
| `colores` | `['rojo','verde','azul','amarillo']` | Catálogo cerrado de colores. |
| `acciones` | `['agarrar','soltar','mover','detener']` | Catálogo cerrado de acciones. |
| `forzar_clasificador` | `false` | `true` = no llama a LAYA (pruebas sin GPU). |

## 6. Verificación y evidencias

| Evidencia | Cómo se genera |
|---|---|
| `evidencias/frases_50.csv` | Plantilla de las 50 frases. |
| `evidencia/laya_prueba.txt` | `python herramientas/probar_laya.py http://<IP>:8000 "agarra el cubo rojo"` (PC). |
| `evidencia/servicio_interpretar.txt` | `ros2 service call /interpretar_orden ...` (normal **y** con `forzar_clasificador: true`). |
| `resultados_calma.csv` / `resultados_carga.csv` | `medir_item1.py` (calma y con los 4 equipos cargando). |
| `evidencia/resumen_calma.txt` / `resumen_carga.txt` | Salida de cada corrida (`... | tee ...`). |
| Tablas de latencia + exactitud + media página de comentario | Se arman con los resúmenes. |

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
- **Clasificador**: falla con **sinónimos no listados** ("agarrame el cubito") o frases sin acción
  clara; además la prioridad es siempre 1.
- **LAYA**: falla con frases **vagas o de doble acción** ("agarra el cubo y déjalo azul") y a veces
  marca mal `permitido`.
- Si hubo `DEGRADADAS`, explica **por qué** (timeout o servidor saturado).

## 7. Problemas comunes
- **Falta `requests`** → `pip3 install requests --break-system-packages`.
- **La Jetson no conecta con LAYA** → firewall TCP 8000 abierto y `LAYA_HOST=0.0.0.0`.
- **Resumen LAYA vacío** → todas las respuestas fueron degradadas (revisa la red).
- **`colcon build` no encuentra `InterpretarOrden`** → revisa el separador `---` del `.srv` y que
  esté en `rosidl_generate_interfaces(...)`.
- **Privacidad** → la clave de LAYA solo por variable de entorno (`LAYA_API_KEY`).
