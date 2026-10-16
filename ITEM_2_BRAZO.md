# ÍTEM 2 — Mover el brazo (broker + orquestador + cámara + poses + pinza)

Implementación de la Pregunta 2 del Parcial JetCobot. **El `broker.py` no se toca**: el orquestador
solo envía *goals* `move_arm` y **suscribe** `/joint_states` en modo lectura.

> **Regla dura (no romper):** el **broker** es el **único** nodo que publica `/joint_states`. El
> orquestador solo **lee** ese tópico y envía *goals*. Si dos nodos publican `/joint_states`, se
> anula el puntaje.

---

## 1. Archivos del ítem 2

| Archivo (`src/arm_broker/arm_broker/`) | Qué hace |
|---|---|
| `broker.py` | Servidor de la acción `move_arm`: admite, encola (FIFO/prioridad), valida con FK y es el ÚNICO publicador de `/joint_states`. **No se modifica.** |
| `orquestador.py` | Orquestador completo: decisión → rechazo previo → cola interna priorizada → cámara → poses → goals troceados → pinza. |
| `poses.py` | Poses de agarre y depósito **en grados** (convención del kit) + `a_radianes()` + `trozar()`. |
| `percepcion_camara.py` | Detección HSV de color y mapa en vivo `color → pos1..pos4` por anclas de píxel. |
| `gripper.py` | Pinza: vía **primaria** acción `gripper_command`, respaldo pymycobot, flag `gripper_habilitada`. |
| `pinza_pymycobot.py` | Control directo de la pinza por puerto serie (respaldo). |
| `intentos.py` | CSV de los 10 intentos + error de cinemática directa en mm. |
| `cliente_texto.py` | Cliente por teclado: llama `/interpretar_orden` y publica en `/orden_decidida`. |

Herramienta de calibración: `herramientas/calibrar_camara.py`.

## 2. Unidades (trampa importante)

```
posiciones de la mesa (GRADOS) --poses.a_radianes()--> goal move_arm (RADIANES)
                                                        │ el broker valida FK/límites/paso en rad
                                                        ▼ broker.mover() → math.degrees()
                                                   /joint_states (GRADOS) → driver sync_plan_nx
```

`MoveArm.action` dice `joint_positions` **(radianes)**. Los goals van en radianes; el broker es
quien vuelve a grados para el driver.

## 3. Datos de calibración ya fijados

### Poses (grados) — `poses.py`
```python
POSICIONES_CUBO = {          # color-agnósticas; el color lo decide la cámara en vivo
  'pos1': [3, -19, -109, 31, 0, -45],   # abajo_derecha
  'pos2': [41, -13, -126, 55, 0, -4],   # abajo_izquierda
  'pos3': [3, -51, -41, 0, 0, -45],     # arriba_derecha
  'pos4': [25, -54, -39, 0, 0, -25],    # arriba_izquierda
}
DESTINOS = {                 # zonas fijas por color
  'amarillo': [73, -56, -36, 0, -1, -33],
  'rojo':     [87, -49, -48, 0, -1, -33],
  'verde':    [106, -43, -55, 0, -1, -33],
  'azul':     [123, -43, -55, 0, -1, -33],
}
POSE_HOME = [0, 0, 0, 0, 0, -45]
POSE_BUSQUEDA = [20, -8, -21, -54, 0, -22]   # la cámara va en el brazo: mira la mesa aquí
```

### Anclas de píxel (imagen 640×480, con el brazo en `POSE_BUSQUEDA`)
```
pos1 = (537, 385)   pos2 = (114, 380)   pos3 = (520, 87)   pos4 = (122, 90)
```

> El **color no influye en la pose**: las anclas y las poses son por **posición**. La cámara
> construye en vivo el mapa `color → posN` (color solo identifica el cubo) y la pose de agarre sale
> de la posición detectada. Separación mínima entre anclas ≈ 290 px > 2×`radio_ancla_px` (70).

**Troceado obligatorio:** con `paso_max_rad:=2.0` en el broker, algunos tramos directos se rechazan
con causa `paso` (p. ej. HOME→pos2 ≈ 2.20 rad, pos1→azul ≈ 2.09 rad). El orquestador trocea cada
tramo con `poses.trozar(..., paso_orquestador_rad=1.5)`: mismas trayectorias rectas en espacio
articular, pero sin rechazos.

## 4. Secuencia por orden ("agarra el cubo rojo")

1. `/orden_decidida` (JSON del ítem 1/3).
2. **Rechazo antes de encolar**: `permitido=False`, objeto/color desconocido, acción no de agarre o
   color sin destino → `rechazos_orquestador.csv` (no se envía ningún goal).
3. Cola **interna priorizada**: `priority = prioridad × 85` (uint8), ordenada por prioridad y FIFO
   dentro del mismo valor. Una secuencia de agarre a la vez.
4. **Ir a `POSE_BUSQUEDA`** (el brazo coloca la cámara frente a la mesa) y esperar a que se asiente.
5. Cámara: localiza el color pedido y devuelve `pos1..pos4`; si no está sobre la mesa → rechazo
   `no_detectado`.
6. `abrir pinza` → goal a la pose del cubo (**troceado**) → `cerrar pinza` → **goal a
   `POSE_BUSQUEDA` (levanta el cubo y despeja la mesa, evita chocar otros cubos)** → goal a la
   zona del color (**troceado**) → `abrir pinza` → volver a `POSE_HOME`.
7. Registro en `intentos.csv`: éxito y error de FK entre la pose de depósito solicitada y la
   alcanzada (leída de `/joint_states`, solo lectura).

---

## 5. Comandos exactos, paso a paso

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
```

### Orden de arranque (una terminal = un nodo)
| Terminal | Nodo | Para qué |
|---|---|---|
| **T1** | `broker` | La cola: recibe goals `move_arm`, valida y es el **único** que publica `/joint_states`. |
| **T2** | `sync_plan_nx` (driver del kit) | Traduce `/joint_states` a órdenes del brazo físico y la pinza. |
| **T3** | `interprete_ordenes` | Ítem 1: convierte una frase en decisión tipada. |
| **T4** | `cliente_texto` (o `transcriptor_voz`) | Envía la frase (teclado o voz). |
| **T5** | `orquestador` | Ítem 2: cámara + poses + pinza; manda los goals al broker. |

Espera ~2–3 s entre uno y otro para que se descubran.

### T1 — Broker (elige UNA política)

**FIFO** (primero en llegar, primero en salir):
```bash
ros2 run arm_broker broker --ros-args -p politica:=fifo -p paso_max_rad:=2.0 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv
```

**Prioridad** (con envejecimiento):
```bash
ros2 run arm_broker broker --ros-args -p politica:=prioridad -p tau_envejecimiento_s:=12.0 -p paso_max_rad:=2.0 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv
```
Debe verse `BROKER LISTO`.

### T2 — Driver del kit
```bash
ros2 run jetcobot_driver sync_plan_nx      # sustituye por el nombre real del driver
```

### T3 — Intérprete de órdenes (ítem 1)
```bash
ros2 run arm_broker interprete_ordenes --ros-args -p laya_url:=http://<IP_DE_TU_PC>:8000 -p timeout_laya_s:=2.0
```
**Parámetro útil para demo:** `-p forzar_clasificador:=true` fuerza el uso exclusivo del clasificador local (evita que LAYA confunda colores, p. ej. "verde"→"rojo").
Si LAYA no responde o se fuerza, cae/va al clasificador (`degradada=True`) y la cadena sigue.

### T4 — Enviar la frase (cliente de texto)
```bash
ros2 run arm_broker cliente_texto
```
Escribe, por ejemplo: `agarra el cubo rojo`. Puedes enviar varias seguidas.

> Alternativa por **voz** (ítem 3): en lugar de `cliente_texto`,
> `ros2 run arm_broker transcriptor_voz --ros-args -p fuente:=archivo -p ruta_audio:=orden_01.wav`
> (ver `DEMO_VOZ_A_BRAZO.md`).

### T5 — Orquestador (ítem 2)
```bash
ros2 run arm_broker orquestador --ros-args \
  -p gripper_habilitada:=true -p accion_pinza:=gripper_command \
  -p paso_orquestador_rad:=1.5 -p usar_camara:=true -p usar_pose_busqueda:=true \
  -p anclas_camara:="['pos1=537,385','pos2=114,380','pos3=520,87','pos4=122,90']"
```
Debe verse: `🔎 POSE_BUSQUEDA: colocando la cámara frente a la mesa`, luego `🤖 Intento N: <color> en
posN → zona <color>` y la secuencia (abrir → cubo → cerrar → zona → abrir → `HOME`), y una fila
nueva en `intentos.csv`.

> Las anclas ya están calibradas con el brazo en `POSE_BUSQUEDA`. Si mueves la cámara,
> **recalíbralas** (sección 6).

---

## 6. Calibrar la cámara (solo si mueves la cámara)

La cámara va montada en el brazo: solo ve bien la mesa con el brazo en
`POSE_BUSQUEDA = [20, -8, -21, -54, 0, -22]`. El calibrador mueve el brazo por el broker:

```bash
python3 herramientas/calibrar_camara.py --mover-brazo --guardar foto_anclas.jpg
```
- **Clic** en los 4 cubos en orden `pos1 → pos2 → pos3 → pos4` (las 4 esquinas fijas de la mesa).
- Teclas: `r` reinicia, `s` guarda foto, `q`/`ESC` termina e imprime la cadena `-p anclas_camara:="[...]"`.
- Sin pantalla (SSH/Jupyter): `python3 herramientas/calibrar_camara.py --headless --mover-brazo`.

Copia la cadena y pégala en el comando de T5 (o actualiza el default en `orquestador.py` y
`percepcion_camara.py`).

---

## 7. Parámetros, explicados

### Broker (T1)
| Parámetro | Ejemplo | Qué significa |
|---|---|---|
| `politica` | `fifo` | Cómo ordena la cola: `fifo` = orden de llegada; `prioridad` = primero el más importante. |
| `tau_envejecimiento_s` | `12.0` | Solo con `prioridad`: `score = prioridad + espera/tau`. Tau grande → manda la prioridad; tau chico → casi FIFO. |
| `cola_max` | `20` | Cuántos pedidos pueden esperar. Si se llena, los nuevos se rechazan (`rechazos.csv`). |
| `paso_max_rad` | `2.0` | Salto máximo por articulación y movimiento. Si se excede, rechaza con causa `paso`. |
| `duracion_movimiento_s` | `5.0` | Duración de cada movimiento (el enunciado pide ≥ 5 s). |
| `pasos_interpolacion` | `1` | Mensajes `/joint_states` por movimiento. `1` = uno al terminar. |
| `archivo_rechazos` | `rechazos.csv` | Dónde anota el broker lo que no puede atender y por qué. |

### Orquestador (T5)
| Parámetro | Ejemplo | Qué significa |
|---|---|---|
| `client_id` | `orquestador` | Nombre del cliente ante el broker. |
| `escala_prioridad` | `85` | `priority = prioridad × escala_prioridad` (uint8). |
| `topico_decision` | `orden_decidida` | Tópico donde el ítem 1/3 publica la decisión (JSON). |
| `acciones_aceptadas` | `['agarrar']` | Acciones que el orquestador atiende. |
| `paso_orquestador_rad` | `1.5` | Tamaño del trozo. Debe ser ≤ `paso_max_rad` del broker. |
| `timeout_goal_s` | `120.0` | Cuánto espera a que el broker termine un goal. |
| `usar_camara` | `true` | Encender la cámara. `false` deja sin percepción → toda orden se rechaza (`no_detectado`); **no hay respaldo**. |
| `usar_pose_busqueda` | `true` | Ir a `POSE_BUSQUEDA` antes de detectar (la cámara va en el brazo). |
| `pose_busqueda` | `[20,-8,-21,-54,0,-22]` | Ángulos de la pose que mira la mesa. |
| `espera_busqueda_s` | `1.0` | Tiempo de asentado tras llegar a `POSE_BUSQUEDA`. |
| `anclas_camara` | `['pos1=537,385', ...]` | Píxeles (x,y) de cada esquina de la mesa (coincidiendo con su pose `posN`). |
| `radio_ancla_px` | `70.0` | Radio (px) para asignar un color a una posición. |
| `frames_estabilidad` | `8` | Cuadros seguidos que debe verse el mismo color. |
| `timeout_color_s` | `8.0` | Cuánto espera a que aparezca el color pedido (si no, rechazo `no_detectado`). |
| `indice_camara` | `-1` | Qué cámara usar (`-1` = automático). |
| `gripper_habilitada` | `true` | Encender el control de la pinza (`false` = no abre/cierra). |
| `accion_pinza` | `gripper_command` | Vía primaria de la pinza (respaldo: `pinza_pymycobot`). |
| `pinza_pos_abierta` / `pinza_pos_cerrada` | `100` / `0` | Posiciones de la pinza. |
| `archivo_rechazos` | `rechazos_orquestador.csv` | Rechazos antes de encolar. |
| `archivo_intentos` | `intentos.csv` | Los 10 intentos + error de FK (mm). Entregable. |
| `archivo_tiempos` | `tiempos_acciones.csv` | Tiempos por acción. |

**Fórmula del envejecimiento:** `score = prioridad + tiempo_esperando/ tau`. Con `tau=12`, un pedido
de prioridad 1 que esperó 24 s vale 3, empatando con uno de prioridad 3 recién llegado; así **nada
se queda esperando para siempre**.

### Cliente de texto (T4)
| Parámetro | Ejemplo | Qué significa |
|---|---|---|
| `topico_decision` | `orden_decidida` | Tópico de la decisión ya interpretada. |
| `forzar_clasificador` | `false` | `true` = no llama a LAYA (pruebas sin GPU). |

---

## 8. Verificación y evidencias

```bash
# Un solo publicador de /joint_states (debe ser arm_broker)
python3 analisis/verificar_publicadores.py
# Cola del broker en vivo
ros2 topic echo /arm/queue_state
```

| Archivo | Lo escribe | Contenido |
|---|---|---|
| `intentos.csv` | orquestador | Los 10 intentos: resultado y, si fue exitoso, `error_mm`. |
| `rechazos_orquestador.csv` | orquestador | Rechazos **antes** de encolar. |
| `rechazos.csv` | broker | Rechazos del broker (p. ej. causa `paso`). |
| `tiempos_acciones.csv` | orquestador | Tiempos por acción. |

**Entregables (Pregunta 2):** bag de la demo · `intentos.csv` (10 intentos) ·
`rechazos_orquestador.csv` · video de 3 min con la cola y el brazo trabajando en paralelo.

**FIFO vs Prioridad (qué comparar):**

| Pregunta | FIFO | Prioridad |
|---|---|---|
| ¿En qué orden se atienden? | Llegada. | `score = prioridad + espera/tau`. |
| ¿Un prioritario adelanta? | No. | Sí. |
| ¿Un poco prioritario espera para siempre? | No aplica. | No: el envejecimiento lo hace subir. |

## 9. Pruebas sin hardware
- **Sin pinza del kit:** `-p gripper_habilitada:=false`.
- **La posición SIEMPRE sale de la cámara:** no hay respaldo `mapa_color_fijo`. Si no hay cámara o
  no se ve el color pedido, la orden se rechaza con `no_detectado`.

## 10. Problemas comunes
- **Rechazo `paso`** → baja `paso_orquestador_rad` (≤ `paso_max_rad` del broker).
- **Color en posición equivocada** → recalibra con el brazo **exactamente** en `POSE_BUSQUEDA`,
  respetando el orden `pos1=abajo_derecha, pos2=abajo_izquierda, pos3=arriba_derecha,
  pos4=arriba_izquierda` (si las anclas quedan espejadas respecto a las poses, el color va a la
  esquina contraria); ajusta `radio_ancla_px`.
- **`gripper_command` no responde** → respaldo `pinza_pymycobot` por puerto serie.
- **No hay MoveIt2/URDF/ros2_control** → la "IK" son las poses precalculadas de `poses.py`.
