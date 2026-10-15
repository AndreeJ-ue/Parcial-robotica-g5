# COMANDOS_RÁPIDOS — Grupo 5

## Primera vez (crea la carpeta `~/anchy`)

```bash
git clone https://github.com/<USUARIO_GITHUB>/<REPO>.git ~/anchy
```

## Entorno (en CADA terminal: JetCobot y PC)

```bash
cd ~/anchy
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash
export ROS_DOMAIN_ID=47
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DISCOVERY_SERVER="<IP_DEL_ROBOT>:11811"
ros2 daemon stop; ros2 daemon start
```

## Comandos por terminal

```bash
# T1 · broker (opción A: FIFO)
ros2 run arm_broker broker --ros-args -p politica:=fifo -p paso_max_rad:=2.0 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv

# T1 · broker (opción B: prioridad)
ros2 run arm_broker broker --ros-args -p politica:=prioridad -p tau_envejecimiento_s:=12.0 -p paso_max_rad:=2.0 -p duracion_movimiento_s:=5.0 -p pasos_interpolacion:=1 -p cola_max:=20 -p archivo_rechazos:=rechazos.csv

# T2 · driver JetCobot
ros2 run jetcobot_driver sync_plan_nx

# T3 · intérprete (ítem 1)
ros2 run arm_broker interprete_ordenes --ros-args -p laya_url:=http://<IP_DE_TU_PC>:8000 -p timeout_laya_s:=2.0

# T4 · cliente de texto
ros2 run arm_broker cliente_texto

# T5 · orquestador (ítem 2)
ros2 run arm_broker orquestador --ros-args -p gripper_habilitada:=true -p accion_pinza:=gripper_command -p paso_orquestador_rad:=1.5 -p usar_camara:=true -p usar_pose_busqueda:=true -p anclas_camara:="['pos1=240,180','pos2=240,340','pos3=400,180','pos4=400,340']"

# T6 · calibrar cámara (brazo en POSE_BUSQUEDA; ver docs/CALIBRAR_CAMARA.md)
python3 herramientas/calibrar_camara.py --mover-brazo --guardar foto_anclas.jpg
```

> Paso a paso completo en `docs/EJECUTAR_ITEM_2.md` y `docs/CALIBRAR_CAMARA.md`.
