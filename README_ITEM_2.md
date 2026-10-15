# Ítem 2 — Agarre autónomo bajo la cola del broker (Pregunta 2, 8 pts)

Implementación de la Pregunta 2 del Parcial Gran Reto JetCobot. **El `broker.py` no se tocó**: el
orquestador del ítem 2 solo envía goals `move_arm` y **suscribe** `/joint_states` en modo lectura.
La regla dura se mantiene: **el único publicador de `/joint_states` es `arm_broker`**.

## Archivos

| Archivo (`src/arm_broker/arm_broker/`) | Qué hace |
|---|---|
| `orquestador.py` | Orquestador completo: decisión → rechazo previo → cola interna priorizada → cámara → poses → goals troceados → pinza. |
| `poses.py` | Poses de agarre y depósito **en grados** (convención del kit) + `a_radianes()` + `trozar()`. |
| `percepcion_camara.py` | Detección HSV de color y mapa en vivo `color → pos1..pos4` por anclas de píxel. |
| `gripper.py` | Pinza: vía **primaria** acción `gripper_command` (`command.position`), respaldo pymycobot, flag `gripper_habilitada`. |
| `pinza_pymycobot.py` | Control directo de la pinza por el puerto serie (vía de respaldo). |
| `intentos.py` | CSV de los 10 intentos + error de cinemática directa `‖FK(q_sol)−FK(q_alc)‖` en mm. |
| `cliente_texto.py` | Cliente por teclado: llama `/interpretar_orden` y publica en `/orden_decidida` (para probar sin voz). |

Entry points nuevos en `setup.py`: `orquestador` (completo) y `cliente_texto`.

Herramienta de calibración: `herramientas/calibrar_camara.py` (ver `docs/CALIBRAR_CAMARA.md`).
Guía de ejecución completa: `docs/EJECUTAR_ITEM_2.md`.

## Unidades (trampa importante)

```
posiciones de la mesa (GRADOS)  --poses.a_radianes()-->  goal move_arm (RADIANES)
                                                          │  el broker valida FK/límites/paso en rad
                                                          ▼  broker.mover() → math.degrees()
                                                     /joint_states (GRADOS) → driver sync_plan_nx
```

`MoveArm.action` dice `joint_positions` **(radianes)**. Los goals van en radianes; el broker es
quien vuelve a grados para el driver. Internamente el orquestador **nunca** escribe grados en un
goal.

## Poses (grados)

```python
POSICIONES_CUBO = {          # el color de cada una lo decide la cámara en vivo
  'pos1': [3, -19, -109, 31, 0, -45],
  'pos2': [41, -13, -126, 55, 0, -4],
  'pos3': [3, -51, -41, 0, 0, -45],
  'pos4': [25, -54, -39, 0, 0, -25],
}
DESTINOS = {                 # zonas fijas por color
  'amarillo': [73, -56, -36, 0, -1, -33],
  'rojo':     [87, -49, -48, 0, -1, -33],
  'verde':    [106, -43, -55, 0, -1, -33],
  'azul':     [123, -43, -55, 0, -1, -33],
}
POSE_HOME = [0, 0, 0, 0, 0, -45]
POSE_BUSQUEDA = [-20, -16, -7, -61, 0, -24]   # la cámara va en el brazo: mira la mesa aquí
```

**Troceado obligatorio:** con `paso_max_rad:=2.0` en el broker, estos tramos directos se rechazan
con causa `paso` (verificado con `fk.paso_articular`):

| Tramo | Paso (rad) |
|---|---|
| HOME→pos2 | 2.20 |
| pos1→azul / pos3→azul | 2.09 |
| azul→HOME | 2.15 |

El orquestador trocea cada tramo con `poses.trozar(..., paso_orquestador_rad=1.5)`: mismas
trayectorias rectas en espacio articular que ya interpola el broker, pero sin rechazos.

## Secuencia por orden ("agarra el cubo rojo")

1. `/orden_decidida` (JSON del ítem 1/3).
2. **Rechazo antes de encolar**: `permitido=False`, objeto/color desconocido, acción no de agarre
   o color sin destino → `rechazos_orquestador.csv` (no se envía ningún goal).
3. Cola **interna priorizada** del orquestador: `priority = prioridad × 85` (uint8), ordenada por
   prioridad y FIFO dentro del mismo valor. Una secuencia de agarre a la vez.
4. **Ir a `POSE_BUSQUEDA`** (el brazo coloca la cámara frente a la mesa) y esperar a que se asiente.
5. Cámara: localiza el color pedido y devuelve `pos1..pos4`; si no está sobre la mesa →
   rechazo `no_detectado` (todavía no se encoló ningún goal al broker).
6. `abrir pinza` → goal a la pose del cubo (**troceado**) → `cerrar pinza` → goal a la zona del
   color (**troceado**) → `abrir pinza` → volver a `POSE_HOME`.
7. Registro en `intentos.csv`: éxito y error de FK entre la pose de depósito solicitada y la
   alcanzada (leída de `/joint_states`, solo lectura).

> La cámara está **montada en el brazo**, por eso la percepción solo es válida en `POSE_BUSQUEDA`.
> Las **anclas de píxel** (`anclas_camara`) se calibran en esa pose; ver
> **`docs/CALIBRAR_CAMARA.md`** y **`docs/EJECUTAR_ITEM_2.md`**.

## Compilar

```bash
cd ~/rb2_ws
colcon build --packages-select arm_broker_interfaces arm_broker --symlink-install
source install/setup.bash
```

## Orden de arranque

```bash
# 1) broker (parámetros del enunciado/kit)
ros2 run arm_broker broker --ros-args \
  -p politica:=prioridad -p tau_envejecimiento_s:=12.0 -p paso_max_rad:=2.0 \
  -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1

# 2) driver del kit (fuera de este repo)
ros2 run <paquete_driver> sync_plan_nx

# 3) intérprete de órdenes (ítem 1)
ros2 run arm_broker interprete_ordenes

# 4) transcripción (ítem 3) o cliente de texto (prueba del ítem 2)
ros2 run arm_broker transcriptor_voz --ros-args -p fuente:=archivo -p ruta_audio:=orden_01.wav
ros2 run arm_broker cliente_texto

# 5) orquestador completo del ítem 2
ros2 run arm_broker orquestador --ros-args \
  -p gripper_habilitada:=true -p accion_pinza:=gripper_command \
  -p paso_orquestador_rad:=1.5 -p usar_pose_busqueda:=true \
  -p anclas_camara:="['pos1=240,180','pos2=240,340','pos3=400,180','pos4=400,340']"
```

> El paso a paso completo por terminal (FIFO y prioridad, con cada parámetro explicado) está en
> **`COMANDOS_ITEM_2.md`**; la ejecución ordenada y la calibración, en **`docs/`**. Las anclas de
> arriba son de ejemplo: calíbralas con **`herramientas/calibrar_camara.py`**
> (ver `docs/CALIBRAR_CAMARA.md`).

Sin cámara calibrada, se puede fijar el mapa a mano: `-p usar_camara:=false
-p mapa_color_fijo:="['rojo=pos1','verde=pos2','azul=pos3','amarillo=pos4']"`.
Sin pinza del kit: `-p gripper_habilitada:=false`.

## Verificación de la regla dura

```bash
python3 analisis/verificar_publicadores.py
# publicadores: 1 · nombres de nodo: ['arm_broker'] → OK
```

## Entregables (Pregunta 2)

- **Bag** de la demostración (cola del broker + brazo bajo pedidos simultáneos).
- **`intentos.csv`**: 10 intentos con su resultado y, por cada intento exitoso, `error_mm`.
- **`rechazos_orquestador.csv`**: rechazos con causa (orden no permitida dictada por el docente).
- **Video** de 3 minutos con la cola del broker y el brazo trabajando en paralelo.

## Pendiente de confirmar en la Jetson

- Que la acción `gripper_command` exista y acepte `command.position` (`ros2 action list | grep -i
  gripper`). Si no responde, el respaldo es `pinza_pymycobot.py`.
- Calibrar las 4 anclas de píxel sobre una foto de la mesa (`anclas_camara`).
