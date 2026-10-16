# Pregunta 3 con LAYA · con comprobaciones previas

Recorrido para la primera vez: micrófono, clave, transcripción, respaldo a teclado y, recién después, la cadena voz → brazo. Si un paso falla, **no seguir**: la tabla del final indica la causa probable. Después se puede usar `PRUEBA_P3_LAYA_DIRECTA.md`.

**Requisito:** la pregunta 2 ya funciona con LAYA (`PRUEBA_P2_LAYA_CON_COMPROBACIONES.md` completa y `config/p2_laya.local.json` confirmada en el Jetson). Esta pregunta solo antepone la voz.

Reparto: **Jetson** = driver, broker, LAYA, cámara. **Raspberry** = micrófono y `transcriptor_voz` (necesita internet para Google AI Studio y red local para ROS).

Antes de cada medición anoten el valor esperado (columna *Predicción*).

---

## 0 · Raspberry: software y entorno

```bash
cd ~/Parcial-robotica
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select arm_broker_interfaces arm_broker parcial_jetcobot
sudo apt install python3-sounddevice python3-numpy alsa-utils      # si faltan
source ./conectar_reto.sh
mkdir -p evidencias
```

## 1 · Micrófono

| # | Comando | Esperado | Obtenido |
|---|---|---|---|
| 1.1 | `arecord -l` | Aparece la tarjeta del micrófono | |
| 1.2 | `python3 -c "import sounddevice as sd; print(sd.query_devices(kind='input'))"` | El dispositivo de entrada por defecto es ese micrófono | |
| 1.3 | `arecord -D plughw:TARJETA,DISPOSITIVO -f S16_LE -r 16000 -c 1 -d 4 evidencias/prueba_mic.wav && aplay evidencias/prueba_mic.wav` | Se escucha la voz grabada | |

`transcriptor_voz` graba con el dispositivo de entrada **por defecto**. Si 1.2 muestra otro, cambiar el predeterminado del sistema (configuración de sonido o `~/.asoundrc`) antes de seguir.

## 2 · Clave y modelo

```bash
read -rsp "Clave de Google AI Studio: " GEMINI_API_KEY; echo; export GEMINI_API_KEY
export GEMINI_MODEL="MODELO_DE_AUDIO_HABILITADO"
git grep -n "AIza" -- . ':!*.md' || echo "sin claves en el repositorio"
```

La última línea debe imprimir *sin claves en el repositorio*: una clave publicada descuenta puntos.

## 3 · Transcripción sola (sin brazo)

En el Jetson solo hace falta el intérprete; para este paso basta con el `launch` en modo simulado:

```bash
# Jetson, T1
ros2 launch parcial_jetcobot parcial.launch.py
```

```bash
# Raspberry
ros2 run parcial_jetcobot transcriptor_voz --ros-args -p client_id:=prueba \
  -p archivo_audio:="$PWD/avances/pregunta_3/orden_01.wav" -p timeout_transcripcion_s:=12.0
```

| # | Esperado | Predicción (s) | Obtenido |
|---|---|---|---|
| 3.1 | En `evidencias/audio/<id>.wav.json`: `modo: voz`, `transcripcion` ≈ "Agarra el cubo rojo", `transcripcion_s` medido | | |
| 3.2 | Mismo JSON: `decision.color: rojo`, `resultado.simulado: true` | | |
| 3.3 | Repetir con micrófono (`-p duracion_audio_s:=5.0`, sin `archivo_audio`) diciendo "recoge el cubo azul" | | |

## 4 · Respaldo a teclado

| # | Prueba | Esperado | Obtenido |
|---|---|---|---|
| 4.1 | `GEMINI_API_KEY= ros2 run parcial_jetcobot transcriptor_voz --ros-args -p client_id:=prueba -p archivo_audio:="$PWD/avances/pregunta_3/orden_01.wav"` | Al instante: *Transcripción no disponible: RuntimeError. Modo texto activo*; escribir la orden y se procesa | |
| 4.2 | `https_proxy=http://10.255.255.1:3128 HTTPS_PROXY=http://10.255.255.1:3128 ros2 run parcial_jetcobot transcriptor_voz --ros-args -p client_id:=prueba -p archivo_audio:="$PWD/avances/pregunta_3/orden_01.wav" -p timeout_transcripcion_s:=5.0` | A los ≈ 5 s pasa a modo texto (simula internet caído sin cortar la red local) | |
| 4.3 | Si es posible, desconectar internet de verdad en el router o punto de acceso y repetir 3.3 | Modo texto; el brazo sigue operable | |

Cerrar el `launch` simulado del Jetson.

## 5 · Cadena real en el Jetson

Como en `PRUEBA_P2_LAYA_CON_COMPROBACIONES.md`, paso 7:

```bash
# T1
python3 integraciones/sync_plan_p2.py
# T2
ros2 launch parcial_jetcobot parcial.launch.py config_file:="$PWD/config/p2_laya.local.json"
# T3
ros2 param set /driver_p2 habilitar_comandos true
ros2 bag record -o evidencias/bag_p3_$(date +%H%M%S) /arm/queue_state /joint_states /arm/joint_states_measured
# T4
ros2 topic echo /arm/queue_state
```

| # | Comprobación | Esperado | Obtenido |
|---|---|---|---|
| 5.1 | `ros2 topic info /joint_states -v` | Un publicador: `arm_broker` | |
| 5.2 | Desde la Raspberry, una orden de texto: `ros2 run parcial_jetcobot cliente_ordenes --ros-args -p client_id:=prueba -p frase:="Recoge el cubo rojo"` | Secuencia completa y el brazo termina **en búsqueda** | |

Con el brazo en búsqueda, percepción, IK y planificación ocurren antes del primer movimiento y el desglose mide lo que pide el enunciado.

## 6 · Ensayo de las cinco órdenes

Una ejecución por orden (graba 5 s; hablar en cuanto aparece *Grabando*):

```bash
ros2 run parcial_jetcobot transcriptor_voz --ros-args -p client_id:=operador \
  -p duracion_audio_s:=5.0 -p timeout_transcripcion_s:=12.0
```

| # | Se dice | Esperado | Predicción | Obtenido |
|---|---|---|---|---|
| 6.1 | Agarra el cubo rojo | Rojo a `zona_rojo` | | |
| 6.2 | Lleva el cubo azul a la zona amarilla | Azul a `zona_amarillo` | | |
| 6.3 | Recoge el cubo verde, es urgente | Verde a `zona_verde`, prioridad 10 | | |
| 6.4 | Agarra el cubo morado | **Objeto que no está en la mesa**: rechazada antes de encolar | | |
| 6.5 | Mueve el brazo fuera de la zona de trabajo | **No permitida**: rechazada antes de encolar | | |

Reponer los cubos después de cada depósito. Para probar también el caso "color retirado de la mesa": quitar el cubo verde y decir "agarra el cubo verde" (va a búsqueda, no lo ve y termina sin accionar la pinza).

## 7 · Fin de habla y desglose

Abrir cada `evidencias/audio/<id>.wav`, ver en qué segundo termina la voz y anotarlo:

```bash
mkdir -p evidencias/p3_anotados
python3 scripts/anotar_fin_habla.py evidencias/audio/<id>.wav.json --offset 2.8 --salida evidencias/p3_anotados/<id>.json
python3 scripts/desglose_voz.py evidencias/p3_anotados/*.json --salida evidencias/p3
```

`desglose_voz.py` suma duraciones medidas en cada máquina: no necesita relojes sincronizados. El envío del goal por la red local queda fuera del total (es del orden de milisegundos).

| Etapa | Predicción (s) | Media obtenida (s) | % |
|---|---|---|---|
| Captura tras fin de habla | | | |
| Transcripción en la nube | | | |
| Decisión (LAYA) | | | |
| Espera en cola | | | |
| Percepción | | | |
| Cinemática inversa (poses enseñadas) | | | |
| Planificación | | | |
| Pinza y asentamiento | | | |
| **Total** | | | |

Para responder con números: la etapa dominante sale de esta tabla. Con grabación fija de 5 s, la *captura tras fin de habla* es tiempo muerto (5 s − fin de habla); bajar `duracion_audio_s` o detectar silencio la reduce a cambio de cortar órdenes largas. Si domina la transcripción, se reduce con audio más corto o un modelo más rápido a cambio de exactitud.

Completar `se_dijo` y `correcta` en `evidencias/p3/ordenes.csv`.

---

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| `Transcripción no disponible: RuntimeError` al instante | Falta `GEMINI_API_KEY`, `GEMINI_MODEL` vacío o inválido, clave rechazada o modelo sin audio |
| `… TimeoutExpired` | Sin internet o la nube no respondió dentro de `timeout_transcripcion_s` |
| `… ValueError` | El archivo de audio no existe, tiene un formato no admitido o la transcripción vino vacía |
| `… ImportError` | Falta `sounddevice` / `numpy` en el Python de ROS |
| Audio en silencio | El dispositivo de entrada por defecto no es el micrófono (paso 1.2) |
| `No aparece /interpretar_orden` | La Raspberry no ve el grafo del Jetson: revisar `conectar_reto.sh` |
| Desglose sin *captura* | Falta anotar el fin de habla (paso 7) o la orden vino de archivo |
| Aviso *alguna orden empezó fuera de búsqueda* | El brazo no estaba en búsqueda; repetir esa orden |
