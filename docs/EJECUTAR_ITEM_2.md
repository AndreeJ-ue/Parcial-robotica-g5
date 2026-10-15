# Ejecutar el Ítem 2 de punta a punta (paso a paso)

Guía completa para correr la demo del Ítem 2: entorno, arranque de todos los nodos, calibración de
cámara y envío de órdenes. Sigue los pasos en orden.

> **Regla dura:** el **broker** es el único nodo que publica `/joint_states`. El orquestador solo
> **lee** ese tópico y envía *goals* `move_arm`. Nunca arranques dos publicadores de `/joint_states`.

---

## 0. Entorno (una vez por terminal)

### 0.1 Primera vez: clonar el repo (crea la carpeta `~/anchy`)

```bash
git clone https://github.com/<USUARIO_GITHUB>/<REPO>.git ~/anchy
```

### 0.2 En cada terminal (`JetCobot` o PC)

```bash
cd ~/anchy
source /opt/ros/humble/setup.bash
colcon build --packages-select arm_broker_interfaces arm_broker --symlink-install
source install/setup.bash
export ROS_DOMAIN_ID=47
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DISCOVERY_SERVER="<IP_DEL_ROBOT>:11811"
ros2 daemon stop; ros2 daemon start
```

Reemplaza `<IP_DEL_ROBOT>` por la IP del JetCobot. Cada terminal nueva necesita el `source` y los
`export` (o ponlos en tu `~/.bashrc`).

### 0.3 Abre las terminales

Vas a usar: **T1** broker, **T2** driver, **T3** intérprete, **T4** cliente, **T5** orquestador, y
**T6** solo para calibración (opcional).

---

## 1. Arrancar los nodos (en este orden)

### T1 — Broker

```bash
# Opción A: FIFO
ros2 run arm_broker broker --ros-args -p politica:=fifo -p paso_max_rad:=2.0 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv

# Opción B: prioridad (envejecimiento con tau)
ros2 run arm_broker broker --ros-args -p politica:=prioridad -p tau_envejecimiento_s:=12.0 -p paso_max_rad:=2.0 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv
```

Se usa **una** de las dos. Espera ver `BROKER LISTO`.

### T2 — Driver del JetCobot

```bash
ros2 run jetcobot_driver sync_plan_nx
```

### T3 — Intérprete de órdenes (Ítem 1)

```bash
ros2 run arm_broker interprete_ordenes --ros-args -p laya_url:=http://<IP_DE_TU_PC>:8000 -p timeout_laya_s:=2.0
```

Si LAYA no responde, cae al clasificador local (`degradada=True`) y la cadena sigue.

### T4 — Enviar la orden (cliente de texto)

```bash
ros2 run arm_broker cliente_texto
```

Escribe, por ejemplo: `agarra el cubo rojo` y pulsa Enter.

### T5 — Orquestador (Ítem 2)

```bash
ros2 run arm_broker orquestador --ros-args \
  -p gripper_habilitada:=true -p accion_pinza:=gripper_command \
  -p paso_orquestador_rad:=1.5 \
  -p usar_camara:=true -p usar_pose_busqueda:=true \
  -p anclas_camara:="['pos1=214,167','pos2=421,163','pos3=232,352','pos4=408,349']"
```

> Las `anclas_camara` de arriba son de **ejemplo**: calíbralas tú (sección 2). Mientras no lo hagas,
> el orquestador no verá bien los colores.

---

## 2. Calibrar la cámara (si aún no lo hiciste)

La cámara va montada en el brazo, así que se calibra **con el brazo en `POSE_BUSQUEDA`**. El propio
calibrador lo mueve por el broker:

```bash
python3 herramientas/calibrar_camara.py --mover-brazo --guardar foto_anclas.jpg
```

Haz **clic en los 4 cubos** en orden `pos1 → pos2 → pos3 → pos4`. Al terminar imprime la cadena
`-p anclas_camara:="[...]"`; pégala en el comando de T5.

Detalle completo en **`docs/CALIBRAR_CAMARA.md`**.

---

## 3. Enviar órdenes y observar

En **T4** escribe varias órdenes (una por línea):

```
agarra el cubo rojo
agarra la esfera verde
agarra el cubo azul
```

En **T5** el flujo esperado por orden:

1. `🔎 POSE_BUSQUEDA: colocando la cámara frente a la mesa`
2. detección de color → `posN` (o rechazo `no_detectado`)
3. `🤖 Intento N: <color> en <posN> → zona <color>`
4. secuencia: abrir pinza → ir al cubo → cerrar pinza → ir a la zona → abrir → `HOME`.

En **T1** verás la cola atendiendo los pedidos (con prioridad se reordenan; con FIFO van en orden).

---

## 4. Verificación

```bash
# Un solo publicador de /joint_states (debe ser arm_broker)
python3 analisis/verificar_publicadores.py

# Cola del broker en vivo
ros2 topic echo /arm/queue_state
```

Archivos generados:

| Archivo | Lo escribe | Contenido |
|---|---|---|
| `intentos.csv` | orquestador | Intentos + `error_mm` por intento exitoso. |
| `rechazos_orquestador.csv` | orquestador | Rechazos antes de encolar. |
| `rechazos.csv` | broker | Rechazos del broker (p. ej. causa `paso`). |
| `tiempos_acciones.csv` | orquestador | Tiempos por meta. |

---

## 5. Sin hardware (para probar la lógica)

- **Sin cámara calibrada:**
  ```bash
  -p usar_camara:=false -p mapa_color_fijo:="['rojo=pos1','verde=pos2','azul=pos3','amarillo=pos4']"
  ```
- **Sin pinza del kit:** `-p gripper_habilitada:=false`
- **Sin cámara:** no se hace la pose de búsqueda (se usa el mapa fijo).

---

## Parámetros clave

| Nodo | Parámetro | Qué hace |
|---|---|---|
| broker | `politica` | `fifo` o `prioridad`. |
| broker | `tau_envejecimiento_s` | Constante de aging en prioridad: `score = prioridad + espera/tau`. |
| broker | `paso_max_rad` | Salto articular máximo por movimiento (rechaza con causa `paso` si se excede). |
| orquestador | `usar_pose_busqueda` | Ir a `POSE_BUSQUEDA` antes de detectar (la cámara está en el brazo). |
| orquestador | `pose_busqueda` | Ángulos de la pose de búsqueda (default `POSE_BUSQUEDA`). |
| orquestador | `espera_busqueda_s` | Tiempo de asentado antes de leer la cámara. |
| orquestador | `paso_orquestador_rad` | Tamaño del trozo (debe ser ≤ `paso_max_rad` del broker). |
| orquestador | `anclas_camara` | Píxeles `pos1..pos4` de la vista de la cámara. |
| orquestador | `radio_ancla_px` | Radio en píxeles para asignar un color a una posición. |
| orquestador | `gripper_habilitada` / `accion_pinza` | Pinza (acción `gripper_command`). |
