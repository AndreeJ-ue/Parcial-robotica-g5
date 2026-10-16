# Pregunta 3 con LAYA · ejecución directa

Para cuando la cadena de la pregunta 2, LAYA y la transcripción ya se comprobaron (ver `PRUEBA_P3_LAYA_CON_COMPROBACIONES.md`). Aquí no se valida nada: se lanza y se dictan las órdenes.

Reparto: el **Jetson** corre la cadena de la P2 (driver, broker, LAYA, cámara). La **Raspberry** tiene el micrófono y corre `transcriptor_voz`, que usa Google AI Studio por internet. La decisión y el movimiento solo usan la red local.

---

## 1 · Jetson: cadena de la pregunta 2

Igual que `PRUEBA_P2_LAYA_DIRECTA.md`, pasos 1 a 3 (config `config/p2_laya.local.json` ya confirmada):

```bash
# T1
python3 integraciones/sync_plan_p2.py
# T2
ros2 launch parcial_jetcobot parcial.launch.py config_file:="$PWD/config/p2_laya.local.json"
# T3
ros2 param set /driver_p2 habilitar_comandos true
ros2 bag record -o evidencias/bag_p3_$(date +%H%M%S) /arm/queue_state /joint_states /arm/joint_states_measured
```

Antes de la primera orden, enviar una orden de texto desde la Raspberry para que el brazo quede en la postura de búsqueda (así todas las órdenes habladas empiezan desde ahí).

## 2 · Raspberry: clave y entorno

```bash
cd ~/Parcial-robotica && source ./conectar_reto.sh
read -rsp "Clave de Google AI Studio: " GEMINI_API_KEY; echo; export GEMINI_API_KEY
export GEMINI_MODEL="MODELO_DE_AUDIO_HABILITADO"      # el que usaron en las pruebas
mkdir -p evidencias
```

La clave solo vive en la terminal: no se escribe en ningún archivo del repositorio.

## 3 · Cinco órdenes habladas

Una ejecución por orden. Al empezar, el nodo graba 5 s: el operador habla en cuanto aparece *Grabando*.

```bash
ros2 run parcial_jetcobot transcriptor_voz --ros-args \
  -p client_id:=operador -p duracion_audio_s:=5.0 -p timeout_transcripcion_s:=12.0
```

Cada ejecución deja en `evidencias/audio/` el audio (`<id>.wav`) y su resultado (`<id>.wav.json`): lo transcrito, la decisión de LAYA, la espera en cola y los tiempos de cada etapa.

Entre las cinco órdenes del docente habrá **un objeto que no está sobre la mesa** (por ejemplo, "agarra el cubo morado", que se rechaza antes de encolar, o el color de un cubo que se retiró, que termina sin accionar la pinza) y **una orden no permitida**, que se rechaza antes de encolar.

## 4 · Fin de habla (para el tramo de captura)

Abrir cada `.wav` (Audacity o similar), anotar en qué segundo termina de hablar el operador y registrarlo:

```bash
mkdir -p evidencias/p3_anotados
python3 scripts/anotar_fin_habla.py evidencias/audio/<id>.wav.json --offset 2.8 --salida evidencias/p3_anotados/<id>.json
```

## 5 · Tabla y desglose

```bash
python3 scripts/desglose_voz.py evidencias/p3_anotados/*.json --salida evidencias/p3
```

- `evidencias/p3/ordenes.csv`: lo transcrito, la decisión y lo que hizo el brazo. Completar `se_dijo` (lo que dictó el docente) y `correcta` (sí/no, incluido el rechazo cuando corresponde).
- `evidencias/p3/desglose.csv` y `desglose.png`: captura, transcripción, decisión, cola, percepción, IK, planificación y pinza, con la etapa dominante.

## 6 · Modo texto sin internet

Simular la caída de internet solo para esta ejecución (la red local sigue funcionando):

```bash
https_proxy=http://10.255.255.1:3128 HTTPS_PROXY=http://10.255.255.1:3128 \
  ros2 run parcial_jetcobot transcriptor_voz --ros-args -p client_id:=operador -p timeout_transcripcion_s:=5.0
```

A los 5 s aparece *Transcripción no disponible… Modo texto activo*; escribir la orden (por ejemplo `Recoge el cubo azul`) y el brazo la ejecuta. Si se puede desconectar internet de verdad (router o punto de acceso) sin perder la red local, mejor: es la demostración que pide el enunciado.

## 7 · Cierre

```bash
ros2 topic info /joint_states -v          # un solo publicador: arm_broker
ros2 param set /driver_p2 habilitar_comandos false
```

Copiar `evidencias/audio`, `evidencias/p3` y el bag a una carpeta versionada (`evidencias/` está en `.gitignore`).
