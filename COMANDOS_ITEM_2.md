# COMANDOS_ITEM_2.md — todos los comandos, por terminal, para el Ítem 2

Guía **para principiantes**: copia y pega los comandos **tal cual**, en el **orden** en que
aparecen. No hace falta saber ROS 2 para seguirla, pero se explica qué hace cada cosa.

Se cubren las **dos políticas** del broker:
- **Bloque A — FIFO**: el primero que llega se atiende primero.
- **Bloque B — Prioridad**: se atiende primero el pedido más prioritario (con "envejecimiento").

> **Regla dura (no romper):** el **broker** es el **único** nodo que publica `/joint_states`.
> El orquestador solo **lee** ese tópico y envía *goals* `move_arm`. Si dos nodos publican
> `/joint_states`, se anula el puntaje del parcial.

---

## 0. Antes de empezar (una sola vez)

### 0.1 Compilar y "activar" el código

En **una** terminal (esta puede ser la T1):

```bash
cd ~/rb2_ws
colcon build --packages-select arm_broker_interfaces arm_broker --symlink-install
source install/setup.bash
```

- `colcon build` **compila** los paquetes `arm_broker_interfaces` (los mensajes/servicios/acciones)
  y `arm_broker` (los nodos).
- `--symlink-install` hace que los cambios de código se vean **sin** recompilar.
- `source install/setup.bash` le dice a tu terminal **dónde quedó** lo compilado. **Hay que
  ejecutarlo en CADA terminal nueva** (o tener un `source` en el `.bashrc`).

### 0.2 Aislar el tráfico (recomendado si hay varios equipos en la red)

Antes de arrancar los nodos, en **cada** terminal:

```bash
export ROS_DOMAIN_ID=7
```

- Es un **número de "canal"**. Dos computadores con el mismo `ROS_DOMAIN_ID` se ven entre sí; con
  distinto número **no** se ven. Sirve para que tu demo no se mezcle con la de otro grupo. Usa el
  que te asigne el docente (aquí, por ejemplo, 7).

### 0.3 Abre 5 terminales

Vas a usar **5 terminales** (T1…T5). En cada terminal nueva, antes de lanzar el nodo:

```bash
cd ~/rb2_ws
source install/setup.bash
export ROS_DOMAIN_ID=7
```

---

## 1. Qué corre en cada terminal

**Una terminal = un nodo.** No abras dos veces el mismo nodo.

| Terminal | Nodo | Para qué sirve |
|---|---|---|
| **T1** | `broker` | La **cola**: recibe goals `move_arm`, valida, y es el **único** que publica `/joint_states`. |
| **T2** | `sync_plan_nx` (driver del kit) | Traduce `/joint_states` a órdenes del **brazo físico** y la **pinza**. |
| **T3** | `interprete_ordenes` | **Ítem 1**: convierte una frase en una **decisión tipada**. |
| **T4** | `cliente_texto` (o `transcriptor_voz`) | **Envía la frase**. `cliente_texto` = escribes por teclado; `transcriptor_voz` = por voz. |
| **T5** | `orquestador` | **Ítem 2**: cámara + poses + pinza; manda los goals al broker. |

**Orden de arranque:** T1 (broker) → T2 (driver) → T3 (intérprete) → T4 (cliente) → T5 (orquestador).
Espera unos 2–3 segundos entre uno y otro para que todos se "descubran".

---

## Bloque A — Política FIFO

### T1 — Broker (FIFO)

```bash
ros2 run arm_broker broker --ros-args \
  -p politica:=fifo \
  -p paso_max_rad:=2.0 \
  -p duracion_movimiento_s:=5.0 \
  -p pasos_interpolacion:=1 \
  -p cola_max:=20 \
  -p archivo_rechazos:=rechazos.csv
```

Qué debe verse: un mensaje del tipo `BROKER LISTO` con la política y el `paso_max_rad` que le
pasaste.

### T2 — Driver del kit

```bash
ros2 run <paquete_driver> sync_plan_nx
```

> `<paquete_driver>` es el paquete del kit (fuera de este repositorio). Sustitúyelo por el nombre
> real que te dé la Jetson. Este es el único nodo que habla con el **brazo físico**.

### T3 — Intérprete de órdenes (Ítem 1)

```bash
ros2 run arm_broker interprete_ordenes --ros-args \
  -p laya_url:=http://127.0.0.1:8000 \
  -p timeout_laya_s:=2.0
```

- Si LAYA **no** está corriendo en tu PC, no pasa nada: el intérprete **cae** al clasificador por
  palabras clave y marca la respuesta como `degradada=True`. La cadena sigue funcionando.

### T4 — Enviar la frase (cliente de texto)

```bash
ros2 run arm_broker cliente_texto
```

Escribe, por ejemplo:

```
agarra el cubo rojo
```

(Pulsa Enter. Puedes enviar varias; el broker las irá atendiendo **en orden de llegada**.)

> Alternativa por **voz** (Ítem 3): en lugar de `cliente_texto`,
> `ros2 run arm_broker transcriptor_voz --ros-args -p fuente:=archivo -p ruta_audio:=orden_01.wav`.

### T5 — Orquestador (Ítem 2)

```bash
ros2 run arm_broker orquestador --ros-args \
  -p gripper_habilitada:=true \
  -p accion_pinza:=gripper_command \
  -p paso_orquestador_rad:=1.5 \
  -p usar_camara:=true \
  -p usar_pose_busqueda:=true \
  -p anclas_camara:="['pos1=240,180','pos2=240,340','pos3=400,180','pos4=400,340']"
```

Qué debe verse: primero `🔎 POSE_BUSQUEDA: colocando la cámara frente a la mesa`, luego el log de la
secuencia por orden: `abrir pinza` → moverse a la pose del cubo → `cerrar pinza` → moverse a la
zona del color → `abrir pinza` → volver a `HOME`, y una fila nueva en `intentos.csv`.

> Las `anclas_camara` de arriba son de **ejemplo**. La cámara va montada en el brazo, así que se
> calibran con el brazo en `POSE_BUSQUEDA`: `python3 herramientas/calibrar_camara.py --mover-brazo`
> (ver **`docs/CALIBRAR_CAMARA.md`**).

---

## Bloque B — Política de prioridad

Igual que el Bloque A, **cambiando solo la T1**. Todo lo demás queda idéntico.

### T1 — Broker (prioridad)

```bash
ros2 run arm_broker broker --ros-args \
  -p politica:=prioridad \
  -p tau_envejecimiento_s:=12.0 \
  -p paso_max_rad:=2.0 \
  -p duracion_movimiento_s:=5.0 \
  -p pasos_interpolacion:=1 \
  -p cola_max:=20 \
  -p archivo_rechazos:=rechazos.csv
```

T2, T3, T4 y T5 son **exactamente** los mismos comandos del Bloque A.

### Enviar varias órdenes para notar la diferencia

Con `prioridad`, envía varias frases **seguidas** (una por línea) en la T4, mezclando prioridades:

```
agarra el cubo rojo
agarra la esfera verde
agarra el cubo azul
```

La **prioridad** de cada frase la decide el **Ítem 1** (el intérprete), no la escribes tú. Con
prioridad, el broker reordena la cola y atiende antes la más prioritaria; con FIFO, las atiende
**en el orden en que llegaron**.

---

## 2. Todos los parámetros, explicados

### 2.1 Parámetros del **broker** (T1)

| Parámetro | Ejemplo | Qué significa (en palabras simples) | Qué pasa si lo cambias |
|---|---|---|---|
| `politica` | `fifo` | **Cómo ordena la cola.** `fifo` = primero en llegar, primero en salir. `prioridad` = primero el más importante. | `prioridad` reordena la cola según la prioridad de cada pedido. |
| `tau_envejecimiento_s` | `12.0` | **Constante de "envejecimiento" (aging)**. Solo se usa con `politica:=prioridad`. Cuanto **más espera** un pedido en la cola, más sube su prioridad efectiva. | `tau` **grande** (p. ej. 60) → la prioridad "manda" mucho tiempo y los pedidos poco prioritarios esperan. `tau` **chico** (p. ej. 2) → todo se atiende casi por orden de llegada. |
| `cola_max` | `20` | **Cuántos pedidos** pueden estar esperando a la vez. | Si se llena, los pedidos nuevos se **rechazan** (quedan en `rechazos.csv`). |
| `paso_max_rad` | `2.0` | **Salto máximo** (en radianes) que puede dar **una** articulación en **un** movimiento. | Si un segmento pide más de esto, el broker lo **rechaza** con causa `paso`. Por eso el orquestador **trocea** los tramos largos (ver `paso_orquestador_rad`). |
| `duracion_movimiento_s` | `5.0` | **Cuánto dura** cada movimiento (segundos). El enunciado pide **≥ 5 s**. | Más pequeño = movimientos más rápidos (y menos seguros). |
| `pasos_interpolacion` | `1` | **Cuántos mensajes** `/joint_states` publica por movimiento (interpolación). | `1` = un mensaje al terminar. Más grande = trayectoria más "suave" publicada, más carga. |
| `archivo_rechazos` | `rechazos.csv` | **Archivo** donde el broker anota los pedidos que **no** puede atender y por qué. | Vacío (`''`) desactiva el registro de rechazos del broker. |

**La fórmula del envejecimiento (aging):** el "puntaje" con que la cola decide a quién atender es

```
score = prioridad + (tiempo_esperando_segundos / tau)
```

- `prioridad` es la del modelo del Ítem 1 (0–3 típicamente).
- `tiempo_esperando` crece mientras el pedido está en la cola.
- Con `tau = 12.0`: un pedido de prioridad **1** que lleva **24 s** esperando vale
  `1 + 24/12 = 3`, o sea **empata** con uno de prioridad **3** recién llegado (`3 + 0 = 3`).
  A partir de ahí, el que llegó antes gana el desempate. Así, **nada se queda esperando para
  siempre**.
- Con `tau` **más grande**, hay que esperar más tiempo para "subir"; con `tau` **más chico**, se
  premia antes al que espera.

### 2.2 Parámetros del **orquestador** (T5)

| Parámetro              | Ejemplo                    | Qué significa                                                                                    | Qué pasa si lo cambias                                                                                            |
| ---------------------- | -------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `client_id`            | `orquestador`              | **Nombre** con que el orquestador aparece ante el broker.                                        | Cámbialo si corres más de un cliente y quieres distinguirlos en las trazas.                                       |
| `escala_prioridad`     | `85`                       | **Multiplicador** para convertir la prioridad del modelo en el número `uint8` del goal.          | `priority = prioridad × escala_prioridad`. No lo escribas a mano: sale de aquí.                                   |
| `topico_decision`      | `orden_decidida`           | **Tópico** donde el Ítem 1/3 publica la decisión (JSON).                                         | Cámbialo solo si el publicador usa otro nombre.                                                                   |
| `acciones_aceptadas`   | `['agarrar']`              | **Acciones** que el orquestador atiende.                                                         | Si metes `soltar`, también ejecutará las de soltar.                                                               |
| `paso_orquestador_rad` | `1.5`                      | **Tamaño del trozo** con que el orquestador parte cada tramo largo.                              | Debe ser **≤ `paso_max_rad`** del broker para que **no** rechace con causa `paso`. Chico = más tramos, más lento. |
| `timeout_goal_s`       | `120.0`                    | **Cuánto espera** el orquestador a que el broker termine un goal.                                | Más grande para tramos lentos; más chico para detectar antes un bloqueo.                                          |
| `usar_camara`          | `true`                     | **Encender** la cámara para saber qué color hay en cada posición.                                | `false` → usa el mapa fijo `mapa_color_fijo`.                                                                     |
| `usar_pose_busqueda`   | `true`                     | **Ir a `POSE_BUSQUEDA` antes de detectar** (la cámara va montada en el brazo).                    | `false` → no mueve a la pose de búsqueda (solo tiene sentido si la cámara es fija).                               |
| `pose_busqueda`        | `[-20,-16,-7,-61,0,-24]`   | **Ángulos** de la pose que mira la mesa.                                                          | Solo cambia si mueves la cámara o el montaje; recalibra las anclas después.                                       |
| `espera_busqueda_s`    | `1.0`                      | **Tiempo de asentado** tras llegar a `POSE_BUSQUEDA` antes de leer.                               | Más grande = más estable pero más lento.                                                                          |
| `anclas_camara`        | `['pos1=240,180', ...]`    | **Píxeles** (x,y) que corresponden a cada posición de la mesa.                                   | **Hay que calibrarlas** con `herramientas/calibrar_camara.py`. Mal calibradas = el brazo va al lugar equivocado.  |
| `radio_ancla_px`       | `70.0`                     | **Radio** (en píxeles) alrededor del ancla para decidir a qué posición pertenece el color visto. | Más grande = más tolerante; más chico = más estricto.                                                             |
| `frames_estabilidad`   | `8`                        | **Cuántos cuadros seguidos** debe ver el mismo color para aceptarlo.                             | Más cuadros = más seguro pero más lento.                                                                          |
| `timeout_color_s`      | `8.0`                      | **Cuánto espera** a que aparezca el color pedido antes de rechazar.                              | Se agota → rechazo `no_detectado`.                                                                                |
| `indice_camara`        | `-1`                       | **Qué cámara** usar. `-1` = la que el sistema elija.                                             | Ponlo en `0`, `1`, … si tienes varias cámaras.                                                                    |
| `mapa_color_fijo`      | `[]`                       | **Mapa manual** color→posición si **no** usas cámara.                                            | Ej.: `"['rojo=pos1','verde=pos2','azul=pos3','amarillo=pos4']"`.                                                  |
| `gripper_habilitada`   | `true`                     | **Encender** el control de la pinza.                                                             | `false` = el brazo se mueve **sin** abrir/cerrar la pinza (útil para probar solo poses).                          |
| `accion_pinza`         | `gripper_command`          | **Vía primaria** de la pinza: la acción `gripper_command`.                                       | El respaldo es el control directo por puerto serie (`pinza_pymycobot`).                                           |
| `pinza_pos_abierta`    | `100`                      | **Posición** de la pinza **abierta** (100).                                                      | Ajusta si tu pinza abre/cierra distinto.                                                                          |
| `pinza_pos_cerrada`    | `0`                        | **Posición** de la pinza **cerrada** (0).                                                        | Ídem.                                                                                                             |
| `pinza_puerto`         | `/dev/ttyUSB0`             | **Puerto serie** de la pinza (solo para la vía de respaldo).                                     | Cámbialo según la Jetson.                                                                                         |
| `pinza_baudios`        | `1000000`                  | **Velocidad** del puerto serie (respaldo).                                                       | Debe coincidir con la del kit.                                                                                    |
| `pinza_velocidad`      | `valor del kit`            | **Velocidad** de la pinza.                                                                       | Más bajo = pinza más lenta y segura.                                                                              |
| `archivo_rechazos`     | `rechazos_orquestador.csv` | **Dónde** anota el orquestador lo que rechaza **antes** de encolar.                              | Así distingues los rechazos del orquestador de los del broker (`rechazos.csv`).                                   |
| `archivo_intentos`     | `intentos.csv`             | **Dónde** anota los 10 intentos y su error de FK (mm).                                           | Es un entregable del parcial.                                                                                     |
| `archivo_tiempos`      | `tiempos_acciones.csv`     | **Dónde** anota los tiempos por acción.                                                          | Útil para medir latencias.                                                                                        |

### 2.3 Parámetros del **cliente de texto** (T4)

| Parámetro | Ejemplo | Qué significa |
|---|---|---|
| `topico_decision` | `orden_decidida` | Tópico al que publica la decisión ya interpretada. |
| `forzar_clasificador` | `false` | `true` = **no** llama a LAYA, usa directo el clasificador local (pruebas sin GPU). |

---

## 3. Qué mirar, cómo comprobarlo

### 3.1 La regla dura (un solo publicador)

En una terminal aparte:

```bash
python3 analisis/verificar_publicadores.py
```

Debe imprimir `publicadores: 1` y `['arm_broker']`. Si sale más de uno, **falla** (anula el
puntaje).

### 3.2 La cola del broker en vivo

```bash
ros2 topic echo /arm/queue_state
```

Muestra el **estado de la cola** (cuántos pendientes y cuáles). Sirve para el video: con FIFO casi
no cambia el orden; con prioridad se ve cómo un pedido prioritario **adelanta** a otros.

### 3.3 Archivos que se generan

| Archivo | Lo escribe | Contenido |
|---|---|---|
| `intentos.csv` | orquestador | Los 10 intentos: resultado y, si fue exitoso, `error_mm` (error de cinemática directa). |
| `rechazos_orquestador.csv` | orquestador | Rechazos **antes** de encolar (no permitido, no detectado, color sin destino…). |
| `rechazos.csv` | broker | Rechazos del broker (p. ej. causa `paso` si algún tramo supera `paso_max_rad`). |
| `tiempos_acciones.csv` | orquestador | Tiempos por acción (para medir latencias). |

### 3.4 Pruebas sin hardware (por si no tienes la cámara o la pinza)

- **Sin cámara calibrada:** `-p usar_camara:=false -p mapa_color_fijo:="['rojo=pos1','verde=pos2','azul=pos3','amarillo=pos4']"`.
- **Sin pinza del kit:** `-p gripper_habilitada:=false`.

---

## 4. FIFO vs Prioridad: qué comparar

| Pregunta | FIFO | Prioridad |
|---|---|---|
| ¿En qué orden se atienden? | Orden de llegada. | Por `score = prioridad + espera/tau`. |
| ¿Un pedido prioritario puede adelantar? | No. | Sí. |
| ¿Un pedido poco prioritario puede esperar para siempre? | No aplica. | No: el envejecimiento lo hace subir. |
| Qué mirar en `queue_state` | Orden estable. | Reordenamientos visibles. |

Para la demo, envía las **mismas** frases en el mismo orden con cada política y compara el orden
real en que el brazo las ejecuta (y el `queue_state`).

---

## 5. Resumen "copiar y pegar"

**FIFO (T1):**
```bash
ros2 run arm_broker broker --ros-args -p politica:=fifo -p paso_max_rad:=2.0 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv
```

**Prioridad (T1):**
```bash
ros2 run arm_broker broker --ros-args -p politica:=prioridad -p tau_envejecimiento_s:=12.0 -p paso_max_rad:=2.0 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv
```

**Driver (T2):** `ros2 run jetcobot_driver sync_plan_nx`

**Intérprete (T3):** `ros2 run arm_broker interprete_ordenes --ros-args -p laya_url:=http://<IP_DE_TU_PC>:8000 -p timeout_laya_s:=2.0`

**Cliente (T4):** `ros2 run arm_broker cliente_texto`

**Orquestador (T5):**
```bash
ros2 run arm_broker orquestador --ros-args -p gripper_habilitada:=true -p accion_pinza:=gripper_command -p paso_orquestador_rad:=1.5 -p usar_camara:=true -p usar_pose_busqueda:=true -p anclas_camara:="['pos1=240,180','pos2=240,340','pos3=400,180','pos4=400,340']"
```

**Calibrar cámara:** `python3 herramientas/calibrar_camara.py --mover-brazo` (ver `docs/CALIBRAR_CAMARA.md`)

**Verificación:** `python3 analisis/verificar_publicadores.py` · **Cola:** `ros2 topic echo /arm/queue_state`
