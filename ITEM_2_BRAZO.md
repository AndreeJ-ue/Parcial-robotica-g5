# ÍTEM 2 — Mover el brazo (broker + percepción + orquestador + poses + pinza)

Implementación de la Pregunta 2 del Parcial JetCobot. **El `broker.py` no se toca**: el orquestador
solo envía *goals* `move_arm` y **suscribe** `/joint_states` en modo lectura.

> **Regla dura (no romper):** el **broker** es el **único** nodo que publica `/joint_states`. El
> orquestador y el nodo de percepción solo **leen** (o no tocan) ese tópico. Si dos nodos publican
> `/joint_states`, se anula el puntaje.

---

## 1. Arquitectura de este ítem

La percepción es un **nodo ROS aparte** (`percepcion_camara`) que mira la cámara y publica el mapa
de colores; el orquestador solo consume ese mapa por tópico. Así visión y movimiento quedan
desacoplados.

```
cámara USB (/dev/videoX)  ─┐
   (fuente=local: OpenCV   │
    la abre él mismo;      ├─► percepcion_camara ─► /objeto_detectado (JSON)
    fuente=driver: se      │     {estación → color}
    suscribe /image_raw)  ─┘

/orden_decidida ──► orquestador ──► goals move_arm ──► broker (cola) ──► /joint_states ──► brazo
                         │                                          (único publicador)
                         └──► pinza: servidor_pinza (acción gripper_command ─► pymycobot serie)
```

### Archivos (`src/arm_broker/arm_broker/`)

| Archivo | Qué hace |
|---|---|
| `broker.py` | Servidor de `move_arm`: admite, encola (FIFO/prioridad), valida con FK y es el ÚNICO publicador de `/joint_states`. **No se modifica.** |
| `estaciones.py` | **Fuente única de verdad**: los 4 rectángulos (ROI) de estación y la pose de agarre de cada una (grados). |
| `poses.py` | Poses base (grados) + `a_radianes()` + `trozar()` + los **planes** (`secuencia_agarrar`, `secuencia_transportar`, `secuencia_completa`, `secuencia_soltar`). |
| `percepcion_camara.py` | **Nodo ROS**: obtiene fotogramas del tópico `/image_raw` (`fuente=driver`) o abriendo la cámara con OpenCV (`fuente=local`); mide el color de cada estación (ROIs) y publica `/objeto_detectado`. Solo publica detección: no mueve el brazo. |
| `orquestador.py` | Orquestador: decisión → rechazo previo → cola priorizada → `POSE_BUSQUEDA` → espera del mapa → planes → pinza. |
| `gripper.py` | Cliente de la pinza: vía **primaria** acción `gripper_command`, respaldo por serie (pymycobot), flag `gripper_habilitada`. |
| `servidor_pinza.py` | **Nodo ROS**: levanta el servidor de la acción `gripper_command` (que el driver del kit no ofrece) y la mueve con `pinza_pymycobot.py`. No publica `/joint_states`. |
| `pinza_pymycobot.py` | Envoltorio del puerto serie de la pinza (pymycobot): `abrir()`, `cerrar()`, `ir_a(0..100)`. Lo usan el servidor y el respaldo de `gripper.py`. |
| `intentos.py` | CSV de los intentos + error de cinemática directa en mm. |
| `cliente_texto.py` | Cliente por teclado: llama `/interpretar_orden` y publica en `/orden_decidida`. |

Herramienta de verificación de visión: `herramientas/calibrar_camara.py`.

## 2. Unidades (trampa importante)

```
poses de la mesa (GRADOS) --poses.a_radianes()--> goal move_arm (RADIANES)
                                                    │ broker valida FK/límites/paso en rad
                                                    ▼ broker.mover() → math.degrees()
                                               /joint_states (GRADOS) → driver sync_plan_nx
```

`MoveArm.action` dice `joint_positions` **(radianes)**. Los goals van en radianes; el broker es
quien vuelve a grados para el driver, y el orquestador vuelve a radianes al **leer** `/joint_states`
para medir el error de FK.

## 3. Datos de calibración fijados

### Estaciones (ROI + pose de agarre) — `estaciones.py`
Resolución de referencia **640×480**. Numeración tal como se ve en la imagen de la cámara:
`1=arriba-izq · 2=arriba-der · 3=abajo-izq · 4=abajo-der`.

```python
ESTACIONES = {
  1: {'roi': (0,   0,   313, 243), 'agarre': [27, -48, -67,  29, 2, -6]},   # arriba-izq
  2: {'roi': (313, 0,   640, 243), 'agarre': [4,  -48, -71,  35, 0, -30]},  # arriba-der
  3: {'roi': (0,   243, 313, 480), 'agarre': [41, -16, -128, 58, 0, 1]},    # abajo-izq
  4: {'roi': (313, 243, 640, 480), 'agarre': [3,  -16, -128, 58, 0, -35]},  # abajo-der
}
```

> Los rectángulos son los **cuadrantes** de la imagen (no hay nada que clicar). Si la resolución
> real difiere de 640×480, `escalar_roi()` los reajusta sola.

### Poses base y destinos — `poses.py`
```python
POSE_HOME     = [0, 0, 0, 0, 0, -45]
POSE_BUSQUEDA = [20, -16, -7, -61, 0, -25]    # la cámara va en el brazo: mira la mesa aquí
POSE_REPARTO  = [93.51, -4.04, -71.54, -12.83, -1.75, -36.29]
DESTINOS = {                                   # zona de depósito fija por color
  'amarillo': [65.12, -72.15, -8.87, -11.77, 5.18, -66.18],
  'rojo':     [80.15, -45.35, -61.78, 12.39,  5.27, -51.24],
  'verde':    [96.15, -35.15, -81.73, 23.37,  5.27, -36.56],
  'azul':     [113.29, -35.15, -81.73, 23.37, 5.27, -18.63],
}
```

> El **color no influye en la pose de agarre**: las poses son por **estación**. La cámara arma en
> vivo el mapa `estación → color` (el color solo identifica el cubo) y la pose de agarre sale de la
> estación donde se vio ese color.

**Troceado obligatorio:** el broker trae `paso_max_rad:=1.2` por defecto. El orquestador trocea cada
tramo con `poses.trozar(..., paso_orquestador_rad=1.0)` (≤ el del broker), así que no hay rechazos
por causa `paso` aunque se corra el broker con su default.

## 4. Secuencia por orden ("agarra el cubo rojo")

1. `/orden_decidida` (JSON del ítem 1/3).
2. **Rechazo antes de encolar**: `permitido=False`, objeto/color desconocido, acción desconocida o
   color sin destino → `rechazos_orquestador.csv` (no se envía ningún goal).
3. Cola **interna priorizada**: `priority = prioridad × 85` (uint8). Una orden completa a la vez.
4. **Ir a `POSE_BUSQUEDA`** (coloca la cámara frente a la mesa).
5. Esperar a que `percepcion_camara` **confirme la ESQUINA** del color pedido (estabilidad por
   esquina en `mapa_confirmado`; una sola esquina parpadeante no bloquea a las demás); si no
   aparece en ninguna estación → rechazo `color_no_encontrado`.
6. `abrir pinza` → goal a la pose de agarre de la estación (**troceado**) → `cerrar pinza` → **goal de
   vuelta a `POSE_BUSQUEDA` (levanta el cubo y despeja la mesa)** → `reparto` → zona del color
   (**troceado**) → `abrir pinza` → `POSE_HOME`.
7. Registro en `intentos.csv`: éxito y error de FK entre la pose de agarre solicitada y la alcanzada
   (leída de `/joint_states`, solo lectura).

**Estados:** si una 'agarrar' terminó bien, el orquestador queda con `cargando=True`; una 'mover'
posterior **no vuelve a agarrar**, solo completa el transporte (`reparto → destino → abrir → home`).
Si una 'agarrar' falla, `cargando` queda en `False`.

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
| **T2** | `sync_plan_nx` (driver del kit) | Traduce `/joint_states` a órdenes del brazo físico. |
| **T2b** | `servidor_pinza` | Levanta la acción `gripper_command` y mueve la pinza por el puerto serie (pymycobot). |
| **T3** | `interprete_ordenes` | Ítem 1: convierte una frase en decisión tipada. |
| **T4** | `cliente_texto` (o `transcriptor_voz`) | Envía la frase (teclado o voz). |
| **T5** | `percepcion_camara` | Ítem 2: mira la cámara y publica el mapa `{estación → color}`. |
| **T6** | `orquestador` | Ítem 2: consume el mapa + planes y manda los goals al broker. |

Espera ~2–3 s entre uno y otro para que se descubran. La percepción toma la cámara de dos formas
(`fuente`): abriéndola con OpenCV (`local`, recomendado si el driver no la abre) o suscribiendo
`/image_raw` si un driver (`usb_cam`) sí publica.

### T1 — Broker (elige UNA política)

**FIFO**:
```bash
ros2 run arm_broker broker --ros-args -p politica:=fifo -p paso_max_rad:=1.2 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv
```
**Prioridad** (con envejecimiento):
```bash
ros2 run arm_broker broker --ros-args -p politica:=prioridad -p tau_envejecimiento_s:=12.0 -p paso_max_rad:=1.2 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv
```
Debe verse el arranque del broker.

### T2 — Driver del kit
```bash
ros2 run jetcobot_driver sync_plan_nx      # sustituye por el nombre real del driver
```

### T2b — Servidor de la pinza (acción `gripper_command`)
El driver del kit no expone la pinza, así que este nodo la levanta por pymycobot:
```bash
ros2 run arm_broker servidor_pinza --ros-args -p puerto:=/dev/ttyUSB0 -p velocidad:=50
```
Debe verse `🖐  pinza -> 100` al abrir y `🖐  pinza -> 15` al cerrar. Como el driver y este nodo
comparten `/dev/ttyUSB0`, comprueba antes quién tiene el puerto (`fuser -v /dev/ttyUSB0`); si no se
puede compartir, corre el orquestador con `-p gripper_habilitada:=false` y sigue el resto de la
cadena.

### T3 — Intérprete de órdenes (ítem 1)
```bash
ros2 run arm_broker interprete_ordenes --ros-args -p laya_url:=http://<IP_DE_TU_PC>:8000 -p timeout_laya_s:=2.0
```
**Parámetro útil para demo:** `-p forzar_clasificador:=true` fuerza el uso exclusivo del clasificador
local (evita que LAYA confunda colores, p. ej. "verde"→"rojo").

### T4 — Enviar la frase (cliente de texto)
```bash
ros2 run arm_broker cliente_texto
```
Escribe, por ejemplo: `agarra el cubo rojo`. Puedes enviar varias seguidas.

### T5 — Percepción (ítem 2)

**Recomendado (la percepción abre la cámara sola, sin depender de un driver):**
```bash
ros2 run arm_broker percepcion_camara --ros-args \
  -p fuente:=local -p topico_salida:=/objeto_detectado -p confirmaciones:=5
```
Debe verse `📷 cámara local abierta en índice N`, luego `📷 primera imagen (cámara local) ...` y, al
moverse el brazo a `POSE_BUSQUEDA`, `🎯 mapa ESTABLE: {...}`.

**Si el driver de la cámara sí publica bien** (p. ej. `usb_cam`), se puede usar el tópico:
```bash
ros2 run arm_broker percepcion_camara --ros-args \
  -p fuente:=driver -p topico_imagen:=/image_raw -p confirmaciones:=5
```

**Modo mixto** (`fuente:=auto`, por defecto): suscribe el tópico y, si no llega ninguna imagen en
`watchdog_s`, abre la cámara local y avisa. Útil cuando el driver arranca pero **no** abre la cámara.

### T6 — Orquestador (ítem 2)
```bash
ros2 run arm_broker orquestador --ros-args \
  -p gripper_habilitada:=true -p accion_pinza:=gripper_command \
  -p paso_orquestador_rad:=1.0 -p usar_camara:=true -p usar_estaciones:=true
```
Debe verse `🔎 yendo a POSE_BUSQUEDA`, luego `📍 color <color> en estación N`, la secuencia
(abrir → agarre → cerrar → búsqueda → reparto → destino → abrir → home) y una fila nueva en
`intentos.csv`.

---

## 6. Verificar la visión (si mueves la cámara o cambias `POSE_BUSQUEDA`)

La cámara va montada en el brazo: solo ve bien la mesa con el brazo en
`POSE_BUSQUEDA = [20, -16, -7, -61, 0, -25]`. El verificador dibuja los 4 rectángulos y muestra el
color de cada estación:

```bash
python3 herramientas/calibrar_camara.py --mover-brazo --guardar foto_estaciones.jpg
python3 herramientas/calibrar_camara.py --headless --mover-brazo   # sin pantalla (SSH/Jupyter)
```
Revisa que cada cubo caiga **dentro de su cuadrante**. No hay anclas que copiar: los rectángulos son
los cuadrantes de la imagen.

---

## 7. Parámetros, explicados

### Broker (T1)
| Parámetro | Ejemplo | Qué significa |
|---|---|---|
| `politica` | `fifo` | Cómo ordena la cola: `fifo` = orden de llegada; `prioridad` = primero el más importante. |
| `tau_envejecimiento_s` | `12.0` | Solo con `prioridad`: `score = prioridad + espera/tau`. Tau grande → manda la prioridad; tau chico → casi FIFO. |
| `cola_max` | `20` | Cuántos pedidos pueden esperar. Si se llena, los nuevos se rechazan (`rechazos.csv`). |
| `paso_max_rad` | `1.2` | Salto máximo por articulación y movimiento. Si se excede, rechaza con causa `paso`. |
| `duracion_movimiento_s` | `5.0` | Duración de cada movimiento (el enunciado pide ≥ 5 s). |
| `pasos_interpolacion` | `1` | Mensajes `/joint_states` por movimiento. `1` = uno al terminar. |
| `archivo_rechazos` | `rechazos.csv` | Dónde anota el broker lo que no puede atender y por qué. |

### Percepción (T5)
| Parámetro | Ejemplo | Qué significa |
|---|---|---|
| `fuente` | `local` | De dónde salen los fotogramas: `driver` (tópico ROS), `local` (OpenCV abre la cámara) o `auto` (tópico y, si no llega, cámara local). |
| `topico_imagen` | `/image_raw` | Tópico que se suscribe cuando `fuente` es `driver`/`auto`. |
| `topico_salida` | `/objeto_detectado` | Dónde publica el mapa de estaciones (JSON). |
| `indice_camara` | `-1` | Cámara para `fuente=local`: `-1` = autodetecta 0..3; si no, el índice forzado. |
| `ancho_camara` / `alto_camara` | `640` / `480` | Resolución que se pide a la cámara local. |
| `area_min` | `300` | Píxeles mínimos del manchón de color para contarlo. |
| `confirmaciones` | `5` | Fotogramas seguidos con el mismo mapa para marcarlo `estable`. |
| `watchdog_s` | `5.0` | Avisa si no llega imagen en este tiempo (y en `auto` dispara la cámara local). |
| `log_estado_periodico_s` | `0.0` | `0` = apagado; `>0` = log cada N s. |

> **Por qué `fuente:=local`:** en el kit el driver puede arrancar pero **no abrir la cámara**, así que
> nadie publica en `/image_raw`. `local` toma el dispositivo (`/dev/videoX`) con OpenCV y no depende
> del driver.

### Orquestador (T6)
| Parámetro | Ejemplo | Qué significa |
|---|---|---|
| `client_id` | `orquestador` | Nombre del cliente ante el broker. |
| `escala_prioridad` | `85` | `priority = prioridad × escala_prioridad` (uint8). |
| `paso_orquestador_rad` | `1.0` | Tamaño del trozo. Debe ser ≤ `paso_max_rad` del broker. |
| `usar_camara` | `true` | Encender la percepción. `false` deja sin mapa → toda orden se rechaza. |
| `usar_estaciones` | `true` | `true` = mapa `{estación → color}`; `false` = modo legado (pose única). |
| `espera_deteccion_s` | `6.0` | Cuánto espera el mapa estable con el color pedido. |
| `timeout_goal_s` | `60.0` | Cuánto espera a que el broker termine un goal. |
| `gripper_habilitada` | `true` | Encender el control de la pinza (`false` = no abre/cierra). |
| `accion_pinza` | `gripper_command` | Acción de la pinza; la sirve el nodo `servidor_pinza` (respaldo directo por serie). |
| `pinza_pos_abierta` / `pinza_pos_cerrada` | `100` / `15` | Posiciones de la pinza (escala del kit 0..100). |
| `topico_decision` | `orden_decidida` | Tópico de la decisión ya interpretada. |
| `topico_deteccion` | `objeto_detectado` | Tópico del mapa de percepción. |
| `archivo_rechazos` | `rechazos_orquestador.csv` | Rechazos antes de encolar. |
| `archivo_intentos` | `intentos.csv` | Los intentos + error de FK (mm). Entregable. |
| `archivo_tiempos` | `tiempos_acciones.csv` | Tiempos por meta enviada. |

**Fórmula del envejecimiento:** `score = prioridad + tiempo_esperando/tau`. Con `tau=12`, un pedido de
prioridad 1 que esperó 24 s vale 3, empatando con uno de prioridad 3 recién llegado; así **nada se
queda esperando para siempre**.

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
# Mapa de percepción en vivo
ros2 topic echo /objeto_detectado
```

| Archivo | Lo escribe | Contenido |
|---|---|---|
| `intentos.csv` | orquestador | Los intentos: resultado y, si fue exitoso, `error_mm`. |
| `rechazos_orquestador.csv` | orquestador | Rechazos **antes** de encolar. |
| `rechazos.csv` | broker | Rechazos del broker (p. ej. causa `paso`). |
| `tiempos_acciones.csv` | orquestador | Tiempos por meta enviada. |

**Entregables (Pregunta 2):** bag de la demo · `intentos.csv` · `rechazos_orquestador.csv` · video de
3 min con la cola y el brazo trabajando en paralelo.

**FIFO vs Prioridad (qué comparar):**

| Pregunta | FIFO | Prioridad |
|---|---|---|
| ¿En qué orden se atienden? | Llegada. | `score = prioridad + espera/tau`. |
| ¿Un prioritario adelanta? | No. | Sí. |
| ¿Un poco prioritario espera para siempre? | No aplica. | No: el envejecimiento lo hace subir. |

## 9. Pruebas sin hardware
- **Sin pinza del kit:** `-p gripper_habilitada:=false` (la pinza se "simula" y la cadena sigue).
- **Sin cámara / sin mapa:** la orden se rechaza (`color_no_encontrado` / `sin_deteccion`); la
  posición SIEMPRE sale de la cámara, no hay respaldo de color fijo.

## 10. Problemas comunes
- **Rechazo `paso`** → baja `paso_orquestador_rad` (≤ `paso_max_rad` del broker; el default 1.0 ya
  es seguro).
- **`color_no_encontrado`** → comprueba con `calibrar_camara.py` que la cámara ve la mesa y que cada
  cubo cae dentro de su cuadrante; verifica que el brazo esté en `POSE_BUSQUEDA`. La percepción
  publica el mapa bajo **dos claves equivalentes** (`mapa_estaciones` y `por_slot`) y el orquestador
  acepta **ambas**, para que no se rechace por desajuste de clave entre versiones. Además publica
  `mapa_confirmado` (solo las esquinas con racha suficiente); el orquestador prefiere esa clave, así
  que una esquina parpadeante ya no impide encontrar el color de otra.
- **No llega imagen / el driver corre pero no abre la cámara** → usa `-p fuente:=local` (la
  percepción abre el dispositivo `/dev/videoX` con OpenCV) o `-p fuente:=auto` para el respaldo
  automático. Revisa `/dev/video*` y el `indice_camara`. Diagnóstico: `ros2 topic hz /image_raw`
  (0 Hz = nadie publica).
- **`gripper_command` no responde / la pinza no se mueve** → levanta el nodo `servidor_pinza` (T2b):
  es quien sirve la acción. Si la acción existe pero la pinza no se mueve, el problema es el puerto
  serie compartido: `fuser -v /dev/ttyUSB0` (¿lo tiene `sync_plan_nx`?) y `ls -l /dev/serial/by-id/`.
  La pinza reintenta abrir el puerto en **modo compartido no exclusivo** (`exclusive=False`), y
  `servidor_pinza` marca `reached_goal=False` en cualquier fallo (un fallo NO se reporta como éxito).
  Mientras se resuelve, `-p gripper_habilitada:=false`.
- **No hay MoveIt2/URDF/ros2_control** → la "IK" son las poses precalculadas de `poses.py`.
