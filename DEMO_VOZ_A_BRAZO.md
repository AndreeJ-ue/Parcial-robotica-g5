# DEMO — De la voz al brazo (cadena completa)

Ejecuta la cadena completa: una **orden hablada** (o un `.wav`) se transcribe, se interpreta y el
**brazo se mueve** según la orden. Es la integración de los 3 ítems.

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
                     │  rechaza permitido=False  │
                     │  cámara + poses + pinza   │
                     └────────────┬─────────────┘
                                  │ goals move_arm
                                  ▼
                          broker (arm_broker)
                         · ÚNICA cola de prioridad
                         · ÚNICO publicador de /joint_states
                                  │
                                  ▼
                       /joint_states ──► driver ──► brazo + pinza
```

## Qué corre en cada máquina
- **PC Windows**: `laya-serve` (decisión tipada, no necesita internet).
- **Jetson (ROS 2)**: `broker`, `sync_plan_nx`, `interprete_ordenes`, `transcriptor_voz`,
  `orquestador`.
- **Google AI Studio (internet)**: solo la transcripción de audio.

---

## Comandos por terminal (paso a paso)

### Entorno (en CADA terminal de la Jetson)
```bash
cd ~/rb2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select arm_broker_interfaces arm_broker --symlink-install
source install/setup.bash
export ROS_DOMAIN_ID=47                     # el que asigne el docente
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DISCOVERY_SERVER="<IP_DEL_ROBOT>:11811"
ros2 daemon stop; ros2 daemon start

# Claves solo por variable de entorno
export GOOGLE_API_KEY="TU_CLAVE"
# export LAYA_API_KEY="..."   # solo si pusiste clave en laya-serve
```

### Paso 0 — PC Windows: levantar LAYA
```powershell
cd C:\laya ; .\.venv\Scripts\Activate.ps1
$env:LAYA_HOST="0.0.0.0"; $env:LAYA_PORT="8000"; $env:LAYA_DEVICE="cuda"; $env:LAYA_PRELOAD="1"
laya-serve
```
Comprueba que la Jetson lo ve: `curl -s http://<IP_DE_TU_PC>:8000/health`.

### T1 — Broker (la cola; único publicador de `/joint_states`)
```bash
ros2 run arm_broker broker --ros-args -p politica:=prioridad -p tau_envejecimiento_s:=12.0 -p paso_max_rad:=2.0 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv
```
(Con `-p politica:=fifo` si prefieres FIFO.)

### T2 — Driver del kit
```bash
ros2 run jetcobot_driver sync_plan_nx
```

### T3 — Intérprete de órdenes (ítem 1)
```bash
ros2 run arm_broker interprete_ordenes --ros-args -p laya_url:=http://<IP_DE_TU_PC>:8000 -p timeout_laya_s:=2.0
```

### T4 — Transcriptor de voz (ítem 3): la LECTURA DEL AUDIO
Es el nodo que lee el audio y lo convierte en la orden que mueve el brazo.

**Por archivo `.wav` (recomendado para la demo):**
```bash
ros2 run arm_broker transcriptor_voz --ros-args \
  -p fuente:=archivo -p ruta_audio:=orden_01.wav \
  -p google_model:=gemini-2.5-flash \
  -p timeout_transcripcion_s:=5.0 -p n_ordenes:=1
```
Cada audio nuevo:
```bash
ros2 run arm_broker transcriptor_voz --ros-args -p ruta_audio:=orden_02.wav -p n_ordenes:=1
```

**Por micrófono / teclado (respaldo):**
```bash
ros2 run arm_broker transcriptor_voz --ros-args -p fuente:=teclado -p n_ordenes:=5
```

> Para grabar los audios: `arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 8 orden_01.wav`.

### T5 — Orquestador (ítem 2): mueve el brazo
```bash
ros2 run arm_broker orquestador --ros-args -p gripper_habilitada:=true -p accion_pinza:=gripper_command -p paso_orquestador_rad:=1.5 -p usar_camara:=true -p usar_pose_busqueda:=true -p anclas_camara:="['pos1=114,380','pos2=537,385','pos3=122,90','pos4=520,87']"
```

---

## Flujo esperado por cada orden

1. **T4**: `✅ [GOOGLE] "<texto>" · <ms>` (o `⚠️ MODO TEXTO POR TECLADO` si falla la nube).
2. **T4**: `🧭 [DECISIÓN] agarrar/<objeto>/<color> p=<prioridad> permitido=True · <ms>`.
3. **T5**: `🔎 POSE_BUSQUEDA: colocando la cámara frente a la mesa`.
4. **T5**: `🤖 Intento N: <color> en posN → zona <color>`.
5. **T5/T2**: secuencia `abrir pinza → ir al cubo → cerrar pinza → ir a la zona → abrir → HOME`.
6. **T1**: la cola atiende los pedidos (con prioridad se reordenan; con FIFO, en orden de llegada).

Cuando la orden **no** se ejecuta, se registra el rechazo:
- `permitido=False` o acción no de agarre → `rechazos_orquestador.csv` (no se encola).
- Color no detectado sobre la mesa → rechazo `no_detectado`.
- Objeto/color desconocido → rechazo `objeto_desconocido`.

## Verificación
```bash
python3 analisis/verificar_publicadores.py     # debe salir 1 publicador: arm_broker
ros2 topic echo /arm/queue_state               # cola en vivo
```
Salidas: `transcripciones.csv` (T4), `intentos.csv` / `rechazos_orquestador.csv` /
`tiempos_acciones.csv` (T5), `rechazos.csv` (T1).

> Regla dura: **solo el broker publica `/joint_states`**. El transcriptor y el orquestador nunca
> publican ese tópico; solo leen `joint_states` y envían goals `move_arm`.
