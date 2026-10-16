# DEMO — De la voz al brazo (cadena completa, ítems 1 + 2 + 3)

Ejecuta la cadena completa: una **orden hablada** (o un `.wav`) se **transcribe** (ítem 3), se
**interpreta** (ítem 1) y el **brazo se mueve** según la orden (ítem 2). Este documento es la guía de
la **demo integrada**; el detalle de cada ítem está en `ITEM_1_INTERPRETE.md`, `ITEM_2_BRAZO.md` y
`ITEM_3_TRANSCRIPCION.md`.

```
audio (.wav)                 frase (texto)
     │                            │
     ▼                            │        PC Windows
transcriptor_voz ──texto──────────┤        ┌───────────────┐
  (ítem 3)                        │◄──HTTP─│  LAYA local   │
                                  │        │ (laya-serve)  │
                                  ▼        └───────────────┘
                        /interpretar_orden (servicio ROS 2, ítem 1)
                                  │
                          decisión tipada
                                  ▼
                          /orden_decidida
                                  │
                     ┌────────────┴────────────┐
                     │  orquestador             │  (ítem 2)
                     │  rechaza permitido=False │
                     │  + percepcion_camara     │
                     │  poses + pinza           │
                      └──┬──────────┬──────────┘
                         │ goals    │ gripper_command
                         │ move_arm ▼
                         │   servidor_pinza ──► pinza (serie)
                         ▼
                  broker (arm_broker)
                 · ÚNICA cola de prioridad
                 · ÚNICO publicador de /joint_states
                         │
                         ▼
               /joint_states ──► driver ──► brazo
```

## Qué corre en cada máquina
- **PC Windows**: `laya-serve` (decisión tipada; no necesita internet una vez cargado el modelo).
- **Jetson (ROS 2)**: `broker`, `sync_plan_nx`, `servidor_pinza`, `interprete_ordenes`,
  `transcriptor_voz`, `percepcion_camara`, `orquestador`.
- **Google AI Studio (internet)**: solo la transcripción de audio (ítem 3).

---

## Comandos por terminal (paso a paso)

### Entorno (en CADA terminal de la Jetson)
```bash
git clone -b final https://github.com/AndreeJ-ue/Parcial-robotica-g5.git ~/anchy

cd ~/anchy
source /opt/ros/humble/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=47                     # el que asigne el docente
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DISCOVERY_SERVER="<IP_DEL_ROBOT>:11811"
ros2 daemon stop; ros2 daemon start

# Claves solo por variable de entorno
export GOOGLE_API_KEY="TU_CLAVE"
# export LAYA_API_KEY="..."   # solo si pusiste clave en laya-serve
```
**Qué hace:** carga ROS 2 + el paquete, fija dominio/middleware/descubrimiento, reinicia el daemon y
deja las claves en el entorno (nunca en el código).

### Compilar una vez (antes de la demo)
```bash
cd ~/anchy
colcon build 
source install/setup.bash
```
**Qué hace:** compila los dos paquetes del proyecto y recarga el entorno. `--symlink-install` enlaza
los `.py`, así no hay que recompilar al editar Python.

### Paso 0 — PC Windows: levantar LAYA
```powershell
cd C:\laya ; .\.venv\Scripts\Activate.ps1
$env:LAYA_HOST="0.0.0.0"; $env:LAYA_PORT="8000"; $env:LAYA_DEVICE="cuda"; $env:LAYA_PRELOAD="1"
laya-serve
```
**Qué hace:** arranca LAYA en la PC escuchando en toda la LAN (`0.0.0.0`), para que la Jetson lo
alcance. Comprueba que la Jetson lo ve: `curl -s http://<IP_DE_TU_PC>:8000/health`.

### T1 — Broker (la cola; único publicador de `/joint_states`)
```bash
ros2 run arm_broker broker --ros-args -p politica:=prioridad -p tau_envejecimiento_s:=12.0 -p paso_max_rad:=1.2 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv
```
**Qué hace:** levanta el servidor de `move_arm` con cola **priorizada** y envejecimiento. Usa
`-p politica:=fifo` si prefieres orden de llegada. **Por qué `paso_max_rad:=1.2`:** es el valor por
defecto y el orquestador trocea a 1.0 (≤ 1.2), así nunca hay rechazos por causa `paso`.

### T2 — Driver del kit
```bash
ros2 run jetcobot_driver sync_plan_nx
```
**Qué hace:** abre el puerto serie del brazo y traduce `/joint_states` (grados) a las órdenes físicas
del brazo.

### T2b — Servidor de la pinza (acción `gripper_command`)
El driver del kit **no** expone la acción de la pinza, así que este nodo la levanta por pymycobot:
```bash
ros2 run arm_broker servidor_pinza --ros-args -p puerto:=/dev/ttyUSB0 -p velocidad:=50
```
**Qué hace:** sirve `control_msgs/GripperCommand` y mueve la pinza por serie (100 = abierta,
15 = cerrada).
> **Ojo con el puerto serie:** `sync_plan_nx` y `servidor_pinza` comparten `/dev/ttyUSB0`. Antes de la
> demo comprueba quién lo tiene (`fuser -v /dev/ttyUSB0`) y que la acción aparezca
> (`ros2 action list -t | grep gripper_command`). La pinza reintenta abrir en **modo compartido no
> exclusivo**; si no se puede compartir, corre el orquestador con `-p gripper_habilitada:=false` para
> demostrar el resto de la cadena sin cerrar la pinza.

### T3 — Intérprete de órdenes (ítem 1)
```bash
ros2 run arm_broker interprete_ordenes --ros-args -p laya_url:=http://<IP_DE_TU_PC>:8000 -p timeout_laya_s:=2.0
```
**Qué hace:** expone `/interpretar_orden`; decide con LAYA y, si vence el timeout, con el clasificador
local (`degradada=True`).

### T4 — Transcriptor de voz (ítem 3): la LECTURA DEL AUDIO
Es el nodo que lee el audio y lo convierte en la orden que mueve el brazo.

**Por archivo `.wav` (recomendado para la demo):**
```bash
ros2 run arm_broker transcriptor_voz --ros-args \
  -p fuente:=archivo -p ruta_audio:=orden_01.wav \
  -p google_model:=gemini-2.5-flash \
  -p timeout_transcripcion_s:=5.0 -p n_ordenes:=1
```
**Qué hace:** transcribe `orden_01.wav` con Google AI Studio, llama `/interpretar_orden` y publica la
decisión en `/orden_decidida`. Cada audio nuevo:
```bash
ros2 run arm_broker transcriptor_voz --ros-args -p ruta_audio:=orden_02.wav -p n_ordenes:=1
```

**Por micrófono / teclado (respaldo):**
```bash
ros2 run arm_broker transcriptor_voz --ros-args -p fuente:=teclado -p n_ordenes:=5
```
**Qué hace:** si la nube falla (sin clave, sin internet, timeout), el nodo avisa y lee `input()`.

> Para grabar los audios: `arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 8 orden_01.wav`.

### T5 — Percepción (ítem 2): mira la cámara
```bash
ros2 run arm_broker percepcion_camara --ros-args -p fuente:=local -p confirmaciones:=5
```
**Qué hace:** abre la cámara con OpenCV y publica el mapa `{estación → color}` en `/objeto_detectado`.
Usa `-p fuente:=local` cuando el driver del kit no abre la cámara; `-p fuente:=driver` si un driver sí
publica en `/image_raw`; `-p fuente:=auto` hace el respaldo automático.

### T6 — Orquestador (ítem 2): mueve el brazo
```bash
ros2 run arm_broker orquestador --ros-args -p gripper_habilitada:=true -p accion_pinza:=gripper_command -p paso_orquestador_rad:=1.0 -p usar_camara:=true -p usar_estaciones:=true
```
**Qué hace:** consume `/orden_decidida` y el mapa, va a `POSE_BUSQUEDA`, resuelve la estación del color
y manda la secuencia de *goals* al broker intercalando la pinza.

---

## Flujo esperado por cada orden

1. **T4**: `✅ [GOOGLE] "<texto>" · <ms>` (o `⚠️ MODO TEXTO POR TECLADO` si falla la nube).
2. **T4**: `🧭 [DECISIÓN] agarrar/<objeto>/<color> p=<prioridad> permitido=True · <ms>`.
3. **T5**: `🎯 mapa ESTABLE: {1: ..., 2: ..., 3: ..., 4: ...}` cuando el brazo está en `POSE_BUSQUEDA`.
4. **T6**: `🔎 yendo a POSE_BUSQUEDA` y `📍 color <color> en estación N`.
5. **T6/T2**: secuencia `abrir pinza → agarre en la estación → cerrar pinza → POSE_BUSQUEDA → reparto →
   zona del color → abrir → HOME`.
6. **T1**: la cola atiende los pedidos (con prioridad se reordenan; con FIFO, en orden de llegada).

Cuando la orden **no** se ejecuta, se registra el rechazo:
- `permitido=False` o acción desconocida → `rechazos_orquestador.csv` (no se encola).
- Color no visto en ninguna estación → rechazo `color_no_encontrado`.
- Objeto/color desconocido → rechazo `objeto_desconocido`.

## Verificación
```bash
python3 analisis/verificar_publicadores.py     # debe salir 1 publicador: arm_broker
ros2 topic echo /arm/queue_state               # cola en vivo
ros2 topic echo /objeto_detectado              # mapa de percepción en vivo
```
**Qué hace:** confirma que hay **un solo** publicador de `/joint_states` (`arm_broker`) y muestra en
vivo la cola y el mapa.

Salidas: `transcripciones.csv` (T4), `intentos.csv` / `rechazos_orquestador.csv` /
`tiempos_acciones.csv` (T6), `rechazos.csv` (T1).

> Regla dura: **solo el broker publica `/joint_states`**. El transcriptor y el orquestador nunca
> publican ese tópico; solo leen `/joint_states` y envían *goals* `move_arm`.
