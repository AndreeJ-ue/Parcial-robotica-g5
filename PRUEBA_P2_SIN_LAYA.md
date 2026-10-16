# Prueba de la pregunta 2 sin LAYA

Objetivo: validar la cadena **orden → cola del broker → cámara → poses → pinza → depósito** antes de conectar LAYA. La decisión la toma el clasificador por palabras clave (`degradada=true`). Recursos: **1 Jetson + 1 Raspberry**; los cuatro "integrantes" se lanzan como cuatro procesos desde la Raspberry.

> Regla que no se rompe en ninguna fase: **un solo nodo publica `/joint_states`** (el broker) y **un solo driver** tiene abierto el puerto serial (`sync_plan_p2.py`).

Antes de cada medición anoten lo que esperan obtener (columna *Predicción*).

---

## Fase 0 · Sin ROS (cualquier máquina)

```bash
cd ~/Parcial-robotica
python3 -B -m unittest discover -s tests -v      # deben pasar todas
python3 -B scripts/demo_offline.py               # 3 órdenes: rojo OK, pelota rechazada, "No recojas" rechazada
```

---

## Fase A · Simulación en la Raspberry (sin brazo)

Valida cola, prioridad con envejecimiento y rechazos. La simulación tarda 1,5 s por movimiento para que la cola se vea.

```bash
# Terminal 1
cd ~/Parcial-robotica
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select arm_broker_interfaces arm_broker parcial_jetcobot
source install/setup.bash
unset ROS_DISCOVERY_SERVER FASTRTPS_DEFAULT_PROFILES_FILE
export ROS_DOMAIN_ID=47 ROS_LOCALHOST_ONLY=1
mkdir -p evidencias
ros2 launch parcial_jetcobot parcial.launch.py          # simulación articular por defecto
```

En cada terminal nueva repitan `source` y las dos variables (`ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY=1`).

| # | Terminal | Comando | Resultado esperado | Predicción | Obtenido |
|---|---|---|---|---|---|
| A1 | 2 | `ros2 topic echo /arm/queue_state` | Mensajes a 5 Hz | | |
| A2 | 3 | `ros2 run parcial_jetcobot cliente_ordenes --ros-args -p client_id:=integrante_1 -p frase:="Recoge el cubo rojo"` | `success=true`, `posicion_id=P1`, `destino=zona_rojo` | | |
| A3 | 3 | `... -p frase:="No recojas el cubo azul"` | Rechazada **antes de encolar** (`aceptado=false`) y motivo en el log del broker | | |
| A4 | 3 | `... -p frase:="Recoge la pelota roja"` | Falla: tipo de objeto no calibrado | | |
| A5 | 3 | `bash scripts/cuatro_clientes.sh` | En A1 se ven hasta 3 pedidos en cola; el amarillo **urgente** (p=10) se atiende antes que los de p=1 que ya esperaban | | |
| A6 | 3 | `ros2 topic info /joint_states -v` | Un solo publicador: `arm_broker` (en simulación no publica comandos porque no hay driver) | | |

Resultados: `evidencias/cliente_N.jsonl`, `evidencias/tareas.jsonl`, `evidencias/broker_eventos.csv`.

**Objeto ausente (opcional):** copien `src/parcial_jetcobot/config/posiciones_fijas.articular.simulacion.json` a `config/sim_ausente.local.json`, pongan `"P1": null` en `mapa_simulado` y relancen con `config_file:=$PWD/config/sim_ausente.local.json`. "Recoge el cubo rojo" debe terminar en *Color solicitado ausente* sin accionar la pinza.

---

## Fase B · Simulación distribuida Jetson ↔ Raspberry (sin brazo)

Igual que A, pero el `launch` corre en el Jetson y los clientes en la Raspberry. Valida el Discovery Server y el dominio asignado.

- Jetson: `ROS_DISCOVERY_SERVER=127.0.0.1:11811`, dominio asignado, `ros2 launch parcial_jetcobot parcial.launch.py`.
- Raspberry: `source ./conectar_reto.sh` y repetir A1, A2 y A5.

Si `ros2 node list` sale vacío en la Raspberry, el problema es de descubrimiento, no del código.

---

## Fase C · Brazo real, paso a paso (en el Jetson)

### C0 · Config local sin LAYA

```bash
cd ~/Parcial-robotica
cp -n src/parcial_jetcobot/config/posiciones_fijas.articular.example.json config/prueba_p2.local.json
python3 - <<'PY'
import json;from pathlib import Path
p=Path('config/prueba_p2.local.json');c=json.loads(p.read_text())
c['interpretacion']['modo']='palabras_clave';p.write_text(json.dumps(c,ensure_ascii=False,indent=2))
PY
python3 scripts/preflight.py --config config/prueba_p2.local.json --real   # lista 11 pendientes; es lo esperado
```

### C1 · Driver solo en lectura

```bash
python3 integraciones/sync_plan_p2.py                              # Terminal 1 (queda abierto)
ros2 topic echo /arm/joint_states_measured --once                  # Terminal 2: seis ángulos en radianes
```

### C2 · Pinza

```bash
ros2 param set /driver_p2 habilitar_comandos true
ros2 service call /arm/accionar_pinza arm_broker_interfaces/srv/AccionarPinza "{abrir: true, timeout_s: 5.0}"
ros2 service call /arm/accionar_pinza arm_broker_interfaces/srv/AccionarPinza "{abrir: false, timeout_s: 5.0}"
python3 scripts/confirmar_config.py --config config/prueba_p2.local.json pinza
```

Esta llamada directa a la pinza **solo se usa para preparar el montaje**. Durante la demo la pinza la acciona únicamente el worker del broker.

### C3 · Poses enseñadas con el broker RB2 (una por una)

```bash
# Terminal 3: broker RB2 normal (todavía NO el launch del parcial)
ros2 run arm_broker broker --ros-args -p politica:=fifo -p duracion_movimiento_s:=1.0 -p pasos_interpolacion:=5
```

1. Llevar el brazo a búsqueda. Primero lean la postura actual en grados (C1) y úsenla en `--desde-grados`:
   ```bash
   python3 scripts/traza_poses.py --config config/prueba_p2.local.json --pose busqueda --desde-grados J1 J2 J3 J4 J5 J6 --salida evidencias/traza_busqueda.csv
   ros2 run arm_broker cliente --ros-args -p client_id:=prueba -p traza:="$PWD/evidencias/traza_busqueda.csv"
   ```
2. Con el brazo en búsqueda, comprobar la cámara (detener antes cualquier otro programa que la use):
   ```bash
   python3 scripts/capturar_colores.py --ancho 640 --alto 480          # crea prueba_camara_<n>/mesa_original.png
   python3 scripts/ver_posiciones_fijas.py --config config/prueba_p2.local.json --imagen prueba_camara_<n>/mesa_original.png --salida evidencias/roi_01
   ```
   Abrir `evidencias/roi_01/regiones.png`: cada rectángulo P1–P4 debe contener su cubo y `mapa.json` debe nombrar los 4 colores. Si está bien:
   `python3 scripts/confirmar_config.py --config config/prueba_p2.local.json busqueda camara`
3. Para cada pose (`P1`…`P4`, `zona_rojo`, `zona_verde`, `zona_azul`, `zona_amarillo`), **con la mano cerca del botón de parada**:
   ```bash
   python3 scripts/traza_poses.py --config config/prueba_p2.local.json --pose P1 --salida evidencias/traza_P1.csv
   ros2 run arm_broker cliente --ros-args -p client_id:=prueba -p traza:="$PWD/evidencias/traza_P1.csv"
   python3 scripts/confirmar_config.py --config config/prueba_p2.local.json P1     # solo si la pinza quedó alineada con el cubo / sobre la zona
   ```
   La traza baja a la pose y vuelve a búsqueda con pasos de 0,25 rad como máximo.
4. `python3 scripts/preflight.py --config config/prueba_p2.local.json --real` → solo debe quedar *intérprete configurado para LAYA* (esperado en esta prueba).
5. **Detener el broker RB2 (Ctrl+C)** antes de la fase C4.

### C4 · Cadena completa

```bash
# Terminal 3 (el driver sigue abierto en la 1)
ros2 launch parcial_jetcobot parcial.launch.py config_file:="$PWD/config/prueba_p2.local.json"
# Terminal 4: evidencia
ros2 bag record -o evidencias/bag_p2_$(date +%H%M%S) /arm/queue_state /joint_states /arm/joint_states_measured
```

Desde la Raspberry (`source ./conectar_reto.sh`):

| # | Prueba | Esperado | Predicción | Obtenido |
|---|---|---|---|---|
| C4.1 | `cliente_ordenes ... -p frase:="Recoge el cubo rojo"` (un solo pedido, supervisado) | Búsqueda → cámara → abrir → P(rojo) → cerrar → búsqueda → zona_rojo → abrir → búsqueda | | |
| C4.2 | Permutar dos cubos y repetir | Va a la nueva posición; el color no fija la pose | | |
| C4.3 | Quitar un cubo y pedirlo | *Color solicitado ausente*; no acciona la pinza | | |
| C4.4 | "No recojas el cubo azul" | Rechazada antes de encolar | | |
| C4.5 | `bash scripts/cuatro_clientes.sh` (con cubos repuestos) | Cola visible en `/arm/queue_state`; el urgente adelanta | | |
| C4.6 | `ros2 topic info /joint_states -v` | **Un solo publicador: `arm_broker`** | | |

Diez intentos y tabla:

```bash
python3 scripts/tabla_intentos.py --tareas evidencias/tareas.jsonl --ultimos 10 --salida evidencias/intentos_prueba.csv
```

Completar `exito_fisico` (sí/no) mirando la mesa: el éxito oficial es el objeto correcto en la zona correcta, no `success=true`. `error_fk_mm` es la distancia entre la FK de la postura medida al depositar y la FK de la solicitada.

---

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| `Postura inicial desconocida` / `estado medido obsoleto` | El driver no publica `/arm/joint_states_measured` o está en otro dominio |
| `sin suscriptor en /joint_states` | Driver cerrado |
| `Comandos deshabilitados en el driver` | Falta `ros2 param set /driver_p2 habilitar_comandos true` |
| `Resolución distinta…` | La cámara no entrega 640×480 |
| `Cámara fuera de la postura de búsqueda` | El brazo no llegó dentro de la tolerancia (0,05 rad); revisar la pose o subir `tolerancia_rad` |
| `El robot no confirmó la postura final a tiempo` | El brazo es más lento que lo planificado; subir `timeout_llegada_s` o bajar `velocidad_articular_rad_s` |
| `Configuración articular incompleta: … no confirmados` | Falta `confirmar_config.py` para esa parte |

`evidencias/` está en `.gitignore`; para entregar, copien los archivos finales a una carpeta versionada o súbanlos con `git add -f`.
