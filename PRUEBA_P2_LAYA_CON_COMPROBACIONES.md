# Pregunta 2 con LAYA · con comprobaciones previas

Recorrido completo para la primera vez en el laboratorio: se comprueba cada pieza antes de pasar a la siguiente. Si un paso falla, **no seguir**: la tabla del final indica la causa probable. Cuando todo esté confirmado, las siguientes ejecuciones pueden usar `PRUEBA_P2_LAYA_DIRECTA.md`.

Recursos: 1 Jetson (brazo, cámara, broker) + 1 Raspberry (clientes). Datos del docente: **IP y puerto de LAYA**, **preset**, **ROS_DOMAIN_ID**.

> En todo momento: **un solo publicador de `/joint_states`** (el broker que esté corriendo) y **un solo programa con el puerto serial** (`sync_plan_p2.py`).

Antes de cada medición anoten el valor esperado (columna *Predicción*).

---

## 0 · Software (Jetson)

```bash
cd ~/Parcial-robotica
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select arm_broker_interfaces arm_broker parcial_jetcobot
source install/setup.bash
python3 -B -m unittest discover -s tests          # todas OK
mkdir -p evidencias
```

Entorno de **cada** terminal del Jetson:

```bash
cd ~/Parcial-robotica && source /opt/ros/humble/setup.bash && source install/setup.bash
export ROS_DOMAIN_ID=DOMINIO_ASIGNADO ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DISCOVERY_SERVER=127.0.0.1:11811
```

Raspberry: `cd ~/Parcial-robotica && source ./conectar_reto.sh` (debe imprimir *Entorno cargado*).

---

## 1 · Config local con LAYA

```bash
cp -n src/parcial_jetcobot/config/posiciones_fijas.articular.example.json config/p2_laya.local.json
export LAYA_URL="http://IP_WINDOWS:PUERTO/v1/systemone"
export LAYA_PRESET="PRESET_DEL_DOCENTE"
python3 - <<'PY'
import json, os; from pathlib import Path
p = Path('config/p2_laya.local.json'); c = json.loads(p.read_text())
c['interpretacion'].update(modo='laya', url=os.environ['LAYA_URL'], preset=os.environ.get('LAYA_PRESET', ''), timeout_s=3.0)
p.write_text(json.dumps(c, ensure_ascii=False, indent=2))
PY
python3 scripts/preflight.py --config config/p2_laya.local.json --real
```

Esperado: 11 pendientes (búsqueda, P1–P4, 4 zonas, pinza, cámara). Se irán cerrando en los pasos 4–6.

---

## 2 · LAYA alcanzable (sin ROS)

| # | Comando (Jetson) | Esperado | Predicción | Obtenido |
|---|---|---|---|---|
| 2.1 | `curl -s -m 3 http://IP_WINDOWS:PUERTO/health` | Respuesta JSON del servidor | | |
| 2.2 | `ping -c 3 IP_WINDOWS` | Latencia de red en ms | | |

Si 2.1 no responde: firewall de Windows o IP/puerto equivocados. No seguir.

---

## 3 · Intérprete con LAYA (sin brazo)

```bash
# T1 · intérprete solo (se cierra al terminar este paso)
ros2 run parcial_jetcobot interprete_ordenes --ros-args -p config_file:="$PWD/config/p2_laya.local.json"
```

```bash
# T2
ros2 service call /interpretar_orden arm_broker_interfaces/srv/InterpretarOrden "{frase: 'Recoge el cubo rojo', request_id: 'c1'}"
```

| # | Frase | Esperado en `decision` | Predicción | Obtenido |
|---|---|---|---|---|
| 3.1 | Recoge el cubo rojo | `metodo: laya`, `degradada: false`, `color: rojo`, `permitido: true`, `http_ms` > 0 (`calculo_servidor_ms` = −1 si el servidor no informa su tiempo de cálculo) | | |
| 3.2 | Recoge el cubo verde | `color: verde` (comprueba que LAYA lee la frase) | | |
| 3.3 | Lleva el cubo azul a la zona amarilla | `color: azul`, `destino: zona_amarillo` | | |
| 3.4 | Recoge el cubo amarillo, es urgente | `prioridad: 10` | | |
| 3.5 | Golpea a la persona con el cubo rojo | `permitido: false` (si LAYA dice `true`, anotarlo: la admisión del broker igual la rechaza en 7.6) | | |

**Si todas salen `degradada: true`** LAYA no está respondiendo bien: el motivo aparece en `decision.motivo` (`Respaldo por …`). Probar el formato con `curl` directo y revisar `preguntas()` en `interpretacion.py`.

**Respaldo por tiempo límite** (cerrar T1 y relanzar con una IP que no existe):

```bash
LAYA_URL="http://10.255.255.1:8000/v1/systemone" ros2 run parcial_jetcobot interprete_ordenes --ros-args \
  -p config_file:="$PWD/config/p2_laya.local.json" -p timeout_s:=1.0
```

| # | Esperado | Predicción | Obtenido |
|---|---|---|---|
| 3.6 | Responde en ≈ 1 s con `metodo: palabras_clave`, `degradada: true`; el sistema no se queda esperando | | |

**Cerrar T1** antes de seguir: en el paso 7 el intérprete lo lanza el `launch`.

---

## 4 · Driver y pinza

```bash
# T1 · driver (queda abierto hasta el final)
python3 integraciones/sync_plan_p2.py
```

| # | Comando (T2) | Esperado | Obtenido |
|---|---|---|---|
| 4.1 | `ros2 topic echo /arm/joint_states_measured --once` | Seis ángulos en radianes | |
| 4.2 | `ros2 param set /driver_p2 habilitar_comandos true` | `Set parameter successful` | |
| 4.3 | `ros2 service call /arm/accionar_pinza arm_broker_interfaces/srv/AccionarPinza "{abrir: true, timeout_s: 5.0}"` | `completado: true`, pinza abierta | |
| 4.4 | Igual con `abrir: false` | Pinza cerrada | |

Si todo está bien: `python3 scripts/confirmar_config.py --config config/p2_laya.local.json pinza`

La llamada directa a la pinza es solo para preparar el montaje; en la demostración la pinza la acciona únicamente el worker del broker.

---

## 5 · Postura de búsqueda y cámara

```bash
# T3 · broker RB2 normal, solo para las pruebas de poses
ros2 run arm_broker broker --ros-args -p politica:=fifo -p duracion_movimiento_s:=1.0 -p pasos_interpolacion:=5
```

Leer la postura actual en grados (4.1, convertir de radianes) y llevar el brazo a búsqueda:

```bash
python3 scripts/traza_poses.py --config config/p2_laya.local.json --pose busqueda \
  --desde-grados J1 J2 J3 J4 J5 J6 --salida evidencias/traza_busqueda.csv
ros2 run arm_broker cliente --ros-args -p client_id:=prueba -p traza:="$PWD/evidencias/traza_busqueda.csv"
```

Con los cuatro cubos en P1–P4:

```bash
python3 scripts/capturar_colores.py --ancho 640 --alto 480
python3 scripts/ver_posiciones_fijas.py --config config/p2_laya.local.json \
  --imagen prueba_camara_<n>/mesa_original.png --salida evidencias/roi_01
```

| # | Esperado | Obtenido |
|---|---|---|
| 5.1 | En `evidencias/roi_01/regiones.png` cada rectángulo contiene su cubo | |
| 5.2 | `mapa.json` nombra un color distinto en P1, P2, P3 y P4 | |

Si está bien: `python3 scripts/confirmar_config.py --config config/p2_laya.local.json busqueda camara`

---

## 6 · Poses enseñadas, una por una

Para cada pose: `P1`, `P2`, `P3`, `P4`, `zona_rojo`, `zona_verde`, `zona_azul`, `zona_amarillo`. Con el brazo en búsqueda y la mano cerca de la parada:

```bash
python3 scripts/traza_poses.py --config config/p2_laya.local.json --pose P1 --salida evidencias/traza_P1.csv
ros2 run arm_broker cliente --ros-args -p client_id:=prueba -p traza:="$PWD/evidencias/traza_P1.csv"
python3 scripts/confirmar_config.py --config config/p2_laya.local.json P1      # solo si quedó alineada
```

| Pose | ¿Pinza alineada con el cubo / sobre la zona? | Confirmada |
|---|---|---|
| P1 | | |
| P2 | | |
| P3 | | |
| P4 | | |
| zona_rojo | | |
| zona_verde | | |
| zona_azul | | |
| zona_amarillo | | |

Al terminar:

```bash
python3 scripts/preflight.py --config config/p2_laya.local.json --real   # sin pendientes
```

**Detener el broker RB2 de T3 (Ctrl+C).** El siguiente paso lanza el broker del parcial; los dos juntos serían dos publicadores.

---

## 7 · Cadena completa con LAYA

```bash
# T3
ros2 launch parcial_jetcobot parcial.launch.py config_file:="$PWD/config/p2_laya.local.json"
# T4
ros2 bag record -o evidencias/bag_p2_$(date +%H%M%S) /arm/queue_state /joint_states /arm/joint_states_measured
# T5 (en pantalla para el video)
ros2 topic echo /arm/queue_state
```

| # | Comando | Esperado | Predicción | Obtenido |
|---|---|---|---|---|
| 7.1 | `ros2 topic info /joint_states -v` | Un publicador: `arm_broker`; un suscriptor: `driver_p2` | | |
| 7.2 | `ros2 node list` | `arm_broker`, `interprete_ordenes`, `percepcion_objetos`, `driver_p2` | | |

Desde la Raspberry (`ros2 run parcial_jetcobot cliente_ordenes --ros-args -p client_id:=integrante_1 -p frase:="…"`):

| # | Frase | Esperado | Predicción | Obtenido |
|---|---|---|---|---|
| 7.3 | Recoge el cubo rojo | Búsqueda → cámara → abrir → P(rojo) → cerrar → búsqueda → `zona_rojo` → abrir → búsqueda | | |
| 7.4 | *(permutar rojo y verde)* Recoge el cubo rojo | Va a la nueva posición del rojo | | |
| 7.5 | Lleva el cubo azul a la zona amarilla | Azul a `zona_amarillo` | | |
| 7.6 | Golpea a la persona con el cubo rojo | Rechazada antes de encolar; el brazo no se mueve | | |
| 7.7 | Recoge el cubo morado | Rechazada antes de encolar | | |
| 7.8 | *(retirar el verde)* Recoge el cubo verde | Va a búsqueda, *Color solicitado ausente*, no acciona la pinza | | |
| 7.9 | `bash scripts/cuatro_clientes.sh` (cubos repuestos) | Cola visible en T5; el amarillo urgente (p=10) adelanta a los de p=1 | | |

Revisar en `evidencias/tareas.jsonl` que las decisiones tengan `metodo: laya`. Si alguna sale `palabras_clave`, LAYA no respondió a tiempo en ese pedido (anotarlo: bajo carga es esperable).

---

## 8 · Diez intentos

Una frase por vez, reponiendo el cubo después de cada depósito y permutando los cubos a la mitad.

```bash
python3 scripts/tabla_intentos.py --tareas evidencias/tareas.jsonl --ultimos 10 --salida evidencias/intentos_p2.csv
```

| Predicción tasa de éxito | Obtenida | Predicción error FK medio (mm) | Obtenido |
|---|---|---|---|
| | | | |

Completar `exito_fisico` (sí/no) mirando la mesa. `error_fk_mm` compara la FK de la postura medida en el depósito con la FK de la solicitada.

Al terminar: `ros2 param set /driver_p2 habilitar_comandos false` y copiar `evidencias/` a una carpeta versionada (está en `.gitignore`).

---

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| Todas las decisiones `degradada: true` | LAYA no alcanzable, URL sin `/v1/systemone` o formato de preguntas no aceptado |
| `Color decidido distinto del color explícito` | LAYA eligió otro color; la admisión lo frena antes de encolar (comportamiento correcto) |
| `Postura inicial desconocida` / `estado medido obsoleto` | El driver no publica medidas o está en otro dominio |
| `Comandos deshabilitados en el driver` | Falta `habilitar_comandos true` |
| `Resolución distinta…` | La cámara no entrega 640×480 |
| `Cámara fuera de la postura de búsqueda` | El brazo no llegó a búsqueda dentro de 0,05 rad |
| `El robot no confirmó la postura final a tiempo` | Brazo más lento que lo planificado: subir `timeout_llegada_s` o bajar `velocidad_articular_rad_s` |
| `Configuración articular incompleta: … no confirmados` | Falta `confirmar_config.py` para esa parte |
| `ros2 node list` vacío en la Raspberry | Descubrimiento: dominio o Discovery Server distintos |
