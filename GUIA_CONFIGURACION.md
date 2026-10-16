# Configuración de Raspberry Jetson LAYA y voz

Para la pregunta 2 usar el procedimiento de [P1–P4 y postura de búsqueda](PREGUNTA_2_POSICIONES_FIJAS.md). La cámara en la garra identifica qué color ocupa cada región y el worker del broker ejecuta las poses articulares enseñadas de esa posición (modo `articular`, sin MoveIt). La ruta MoveIt se conserva como alternativa (`"ejecucion": "moveit"`). La antigua ruta de homografía fue retirada.

Esta guía usa el repositorio [Parcial-robotica](https://github.com/AndreeJ-ue/Parcial-robotica). Las órdenes de Raspberry y Jetson se ejecutan en Bash; las de Windows se identifican como PowerShell. Usa equipos autorizados del laboratorio y la IP, dominio, puerto y preset asignados a la reserva actual. `47` corresponde al RB2 del equipo 5; `112` fue utilizado en la última sesión con `.17`. Elige el valor asignado para la sesión, no una IP histórica.

## 1 Descargar los archivos cuando el equipo no los tiene

En Raspberry o Jetson, con Ubuntu 22.04 y ROS 2 Humble:

```bash
cd ~
git clone https://github.com/AndreeJ-ue/Parcial-robotica.git
cd ~/Parcial-robotica
```

Si la carpeta ya existe, trabaja en ella. Para traer cambios de GitHub, guarda primero tus modificaciones locales y usa `git pull --ff-only` dentro de la carpeta. Si el repositorio es privado, usa tu acceso de GitHub sin escribir tokens en archivos compartidos. Los archivos nuevos de esta actualización estarán disponibles para descargar después de subirlos al repositorio.

Comprueba que ROS esté instalado con `source /opt/ros/humble/setup.bash`. Para un equipo nuevo sin ROS, sigue la [instalación oficial de Humble para Ubuntu](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html); Raspberry Pi OS no utiliza directamente estos paquetes de Ubuntu. No se necesita reinstalar ROS en los equipos ya configurados del laboratorio.

## 2 Dependencias y compilación del proyecto principal

En cada Raspberry que ejecutará los paquetes principales:

```bash
cd ~/Parcial-robotica
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --packages-select arm_broker_interfaces arm_broker parcial_jetcobot
source install/setup.bash
mkdir -p evidencias
```

`rosdep` y `colcon` deben estar instalados; en Ubuntu se proporcionan mediante `python3-rosdep` y `python3-colcon-common-extensions`. `rosdep init` se realiza solo una vez por equipo, y después se utiliza `rosdep update`.

Para visión, gráficas y grabación desde micrófono pueden utilizarse las dependencias del sistema:

```bash
sudo apt install python3-numpy python3-opencv python3-matplotlib python3-sounddevice python3-requests alsa-utils
```

Las alternativas con pip están descritas en `requirements-offline.txt` y `requirements-voz.txt`; instala paquetes en el entorno de Python que realmente ejecuta ROS. Para la transcripción independiente sin ROS puedes crear un entorno virtual con acceso a los paquetes del sistema.

En cada terminal nueva carga ROS y la instalación correspondiente. Si el reloj está desfasado, corrígelo desde una fuente actual; `sudo timedatectl set-ntp true` habilita sincronización cuando la red la permite. No copies `build`, `install` o `log` desde otra máquina.

## 3 Raspberry sin Jetson

### Desarrollo local del proyecto principal

No requiere Discovery Server ni puerto serial. En una terminal nueva:

```bash
cd ~/Parcial-robotica
unset ROS_DISCOVERY_SERVER FASTRTPS_DEFAULT_PROFILES_FILE FASTDDS_DEFAULT_PROFILES_FILE
export ROS_DOMAIN_ID=47
export ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash
source install/setup.bash
mkdir -p evidencias
ros2 launch parcial_jetcobot parcial.launch.py
```

El lanzamiento predeterminado utiliza la configuración simulada. En otra terminal, repite las mismas variables y los dos `source`, y envía una orden:

```bash
ros2 run parcial_jetcobot cliente_ordenes --ros-args -p client_id:=integrante_1 -p frase:="Recoge el cubo rojo y deposítalo en la zona a"
```

Para distribuir clientes entre Raspberry sin Jetson, utiliza `ROS_LOCALHOST_ONLY=0` y el mismo dominio autorizado en todas. Sin `ROS_DISCOVERY_SERVER`, ROS utiliza descubrimiento multicast; la red debe permitirlo. Si el laboratorio exige un Discovery Server, utiliza el servidor y el perfil XML que entregue el encargado.

### Interpretación y voz del avance P1/P3

Para ejecutar los programas de las preguntas 1 y 3, compila su workspace independiente desde una terminal nueva:

```bash
source /opt/ros/humble/setup.bash
cd ~/Parcial-robotica/avances/codigo_p1_p3
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

Este workspace utiliza `jetcobot_p13` y `jetcobot_p13_interfaces`. `avances/COLCON_IGNORE` evita que la compilación principal entre en él; al compilar directamente desde `avances/codigo_p1_p3` se descubren sus dos paquetes. Para reproducir interpretación y voz no se necesita Jetson ni iniciar un broker.

En la misma Raspberry establece el entorno local:

```bash
unset ROS_DISCOVERY_SERVER FASTRTPS_DEFAULT_PROFILES_FILE FASTDDS_DEFAULT_PROFILES_FILE
export ROS_DOMAIN_ID=47
export ROS_LOCALHOST_ONLY=1
export LAYA_BASE_URL="http://IP_DEL_WINDOWS:8000"
ros2 run jetcobot_p13 interprete_ordenes --ros-args -p laya_url:="$LAYA_BASE_URL" -p timeout_laya_s:=3.0
```

Sustituye `IP_DEL_WINDOWS` por la IP real del servidor LAYA. `ROS_LOCALHOST_ONLY=1` limita ROS al equipo local y no impide la petición HTTP a Windows. Cuando cliente e intérprete estén en Raspberry distintas, usa `ROS_LOCALHOST_ONLY=0`, igual dominio y red autorizada.

En otra terminal carga ROS y `avances/codigo_p1_p3/install/setup.bash`, repite las variables ROS y llama al servicio aislado:

```bash
ros2 service call /p13/interpretar_orden jetcobot_p13_interfaces/srv/InterpretarOrden "{frase: 'agarra el cubo rojo', forzar_clasificador: false}"
```

Para seleccionar explícitamente el clasificador local cambia `forzar_clasificador` a `true`. El proyecto principal utiliza otro contrato: no intercambies este comando con el servicio `/interpretar_orden` de `parcial_jetcobot`.

## 4 LAYA en Windows y acceso desde Raspberry

En el examen utiliza el servidor del laboratorio con sus valores asignados. Si preparas un servidor propio fuera de ese entorno, en PowerShell:

```powershell
py -3.11 -m venv .venv-laya
.\.venv-laya\Scripts\python.exe -m pip install "laya[serve]"
$env:LAYA_HOST="0.0.0.0"
$env:LAYA_PORT="8000"
$env:LAYA_MODELS="multilingual"
$env:LAYA_PRELOAD="1"
.\.venv-laya\Scripts\laya-serve.exe
```

Espera a que el servidor termine la carga del modelo. La primera instalación necesita descargarlo. Usa `ipconfig` para encontrar la IP de Windows y, si se requiere acceso de red, habilita el puerto únicamente en la red autorizada. `0.0.0.0` es la dirección de escucha; el cliente utiliza la IP real de Windows. `localhost` sirve cuando cliente y servidor están en la misma máquina.

El endpoint de decisión es `/v1/systemone`. La petición incluye `state: {"body": frase}` y preguntas tipadas `choice`, `score` y `noul`. El campo `noul` es una probabilidad que el cliente convierte a permiso. Referencia: [servidor HTTP de LAYA](https://github.com/NandhaKishorM/laya#http-server).

El avance P1/P3 recibe una **URL base**, por ejemplo `http://IP_DEL_WINDOWS:8000`, y agrega `/v1/systemone`. El proyecto principal recibe la **URL completa**, por ejemplo `http://IP_DEL_WINDOWS:8000/v1/systemone`. No agregues el endpoint dos veces.

### Configuración LAYA del proyecto principal

Desde la raíz, crea una configuración local sin alterar el ejemplo compartido:

```bash
cd ~/Parcial-robotica
export LAYA_URL="http://IP_DEL_WINDOWS:8000/v1/systemone"
export LAYA_MODEL="multilingual"
python3 - <<'PY'
import json, os
from pathlib import Path
p=Path('src/parcial_jetcobot/config/posiciones_fijas.articular.simulacion.json')
c=json.loads(p.read_text())
c['interpretacion'].update(modo='laya',url=os.environ['LAYA_URL'],modelo=os.environ['LAYA_MODEL'])
Path('config/laya.local.json').write_text(json.dumps(c,ensure_ascii=False,indent=2))
PY
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run parcial_jetcobot interprete_ordenes --ros-args -p config_file:="$PWD/config/laya.local.json"
```

El ejemplo mantiene el modo superior `simulado`; cambiar el intérprete a LAYA no activa por sí solo movimiento real. Si inicias el lanzamiento completo con esa configuración, no mantengas otro intérprete principal ejecutándose:

```bash
ros2 launch parcial_jetcobot parcial.launch.py config_file:="$PWD/config/laya.local.json"
```

Para el servidor del laboratorio, utiliza el modelo y preset entregados por el docente. El adaptador P1/P3 y el proyecto principal utilizan sus respectivos contratos, preguntas y catálogos.

## 5 Repetir mediciones de la pregunta 1

Con el intérprete P1/P3 activo y el workspace correspondiente cargado:

```bash
cd ~/Parcial-robotica/avances/codigo_p1_p3
mkdir -p resultados
python3 herramientas/medir_item1.py "../pregunta_1/Copia de frases_50.csv" "resultados/calma_$(date +%Y%m%d_%H%M%S).csv"
```

Para carga, cada terminal usa un nombre de archivo distinto. Conserva los CSV recibidos en `avances/pregunta_1/` como originales. El medidor heredado registra estimaciones de red/cómputo obtenidas mediante `/health`; interpreta esos campos como estimaciones. La respuesta normal puede proceder del respaldo: identifica siempre `laya_degradada` y `fuente`.

## 6 Voz de la pregunta 3

Configura la clave en cada terminal donde ejecutes voz, sin escribirla en el repositorio:

```bash
read -rsp "Clave de Google AI Studio: " GOOGLE_API_KEY
echo
export GOOGLE_API_KEY
read -rp "Modelo de audio habilitado: " GOOGLE_MODEL
export GOOGLE_MODEL
```

Los registros de sesión muestran `gemini-3.5-flash`. Selecciona un modelo de audio habilitado para la cuenta que estés utilizando. El nombre se pasa como parámetro y no se utiliza como prueba de disponibilidad actual. Referencia: [audio en Gemini](https://ai.google.dev/gemini-api/docs/audio).

### Transcripción sin ROS ni Jetson

Con Python y `requests` instalados, desde `avances/codigo_p1_p3`:

```bash
python3 herramientas/transcribir_audio.py ../pregunta_3/orden_01.wav "$GOOGLE_MODEL"
```

Puede ejecutarse en Raspberry o en Windows; en PowerShell configura `$env:GOOGLE_API_KEY` y `$env:GOOGLE_MODEL` en el entorno local. Los audios del repositorio ya pueden utilizarse directamente.

### Audio hacia el intérprete P1/P3

Deja activo el intérprete de la sección 3. En otra terminal carga ROS y su instalación, conserva igual dominio y `ROS_LOCALHOST_ONLY`, configura la clave y ejecuta:

```bash
cd ~/Parcial-robotica/avances/codigo_p1_p3
source /opt/ros/humble/setup.bash
source install/setup.bash
mkdir -p resultados
ros2 run jetcobot_p13 transcriptor_voz --ros-args -p fuente:=archivo -p ruta_audio:="$HOME/Parcial-robotica/avances/pregunta_3/orden_01.wav" -p google_model:="$GOOGLE_MODEL" -p timeout_transcripcion_s:=30.0 -p csv_transcripciones:="$PWD/resultados/transcripciones.csv"
```

Para escribir la orden, usa `-p fuente:=teclado` en lugar de `archivo`. El modo de teclado también se ofrece ante fallo de transcripción. El nodo entrega la decisión al tópico `/p13/orden_decidida`. Este workspace no incluye un nodo que convierta esas decisiones en movimientos.

Para grabar otro WAV, primero consulta `arecord -l` y elige el dispositivo real. Un ejemplo es `arecord -D plughw:TARJETA,DISPOSITIVO -f S16_LE -r 16000 -c 1 -d 5 orden_nueva.wav`, sustituyendo el par después de `plughw:` por los números de tarjeta y dispositivo correctos.

### Voz del proyecto principal

El proyecto principal usa las variables `GEMINI_API_KEY` y `GEMINI_MODEL`. Puedes reutilizar los valores de la terminal:

```bash
export GEMINI_API_KEY="$GOOGLE_API_KEY"
export GEMINI_MODEL="$GOOGLE_MODEL"
```

Carga la instalación principal, deja activo su lanzamiento y usa:

```bash
cd ~/Parcial-robotica
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run parcial_jetcobot transcriptor_voz --ros-args -p config_file:="$PWD/config/laya.local.json" -p archivo_audio:="$PWD/avances/pregunta_3/orden_01.wav"
```

Este cliente sí utiliza la ruta de tareas principal; el comportamiento físico depende del modo y configuración cargados en el broker.

## 7 Raspberry con Jetson

Cada equipo compila sus propias fuentes. En la Raspberry configura la conexión del proyecto principal:

```bash
cd ~/Parcial-robotica
cp -n config/equipo.env.example config/equipo.env
cp -n config/super_client.example.xml config/super_client.local.xml
nano config/equipo.env
```

Completa `JETSON`, `ROS_DOMAIN_ID`, `DISCOVERY_PORT` y la ruta absoluta de `FASTRTPS_DEFAULT_PROFILES_FILE`. En `config/super_client.local.xml`, cambia únicamente la dirección y el puerto del `RemoteServer` para que coincidan con el Jetson asignado. La plantilla corresponde al servidor de descubrimiento con ID 0. Luego:

```bash
source ./conectar_reto.sh
```

El script mantiene la comprobación del XML porque forma parte de la carga de conexión. En otras Raspberry del equipo configura la misma IP, puerto y dominio, con el perfil XML local de cada una.

En el Jetson descarga el mismo repositorio directamente y compila:

```bash
cd ~/Parcial-robotica
source /opt/ros/humble/setup.bash
colcon --log-base log_jetson build --build-base build_jetson --install-base install_jetson --symlink-install --packages-select arm_broker_interfaces arm_broker parcial_jetcobot
source install_jetson/setup.bash
```

Si el Discovery Server está ejecutándose en ese Jetson, configura su terminal con el dominio asignado y `ROS_DISCOVERY_SERVER=127.0.0.1:11811`; la Raspberry utiliza `IP_DEL_JETSON:11811`. El puerto debe coincidir con la reserva. No inicies otro servidor si el laboratorio ya lo tiene activo. Para preparar uno en un entorno propio autorizado, consulta la [guía oficial de Discovery Server](https://docs.ros.org/en/humble/Tutorials/Advanced/Discovery-Server/Discovery-Server.html).

La copia de los archivos entre equipos, cuando GitHub no esté accesible, debe incluir las fuentes y excluir los directorios generados. Si el Jetson tiene acceso a GitHub, utiliza el `git clone` directo de la sección 1.

## 8 Driver broker y cámara

El driver adaptado requiere `pymycobot` y la configuración serial correspondiente al brazo. Cierra la conexión serial del notebook antes de usar un driver; usa un único driver a la vez.

En el Jetson, con su instalación y entorno ROS cargados:

```bash
cd ~/Parcial-robotica
python3 integraciones/sync_plan_p2.py
```

Al iniciar lee ángulos; los comandos están deshabilitados por defecto. La medición se publica en `/arm/joint_states_measured` y la pinza usa `/arm/accionar_pinza`. El driver original `sync_plan_nx.py` del laboratorio también recibe comandos articulares, pero sus funciones dependen de la versión instalada.

Para usar el broker articular, carga el entorno del equipo y ejecuta una única instancia:

```bash
mkdir -p evidencias
ros2 run arm_broker broker --ros-args -p politica:=fifo -p archivo_eventos:="$PWD/evidencias/cola_$(date +%Y%m%d_%H%M%S).csv"
```

Si se utiliza el driver adaptado, su activación se hace expresamente con `ros2 param set /driver_p2 habilitar_comandos true` una vez preparada la postura y el recorrido. Para deshabilitarlo usa el mismo comando con `false`.

La cámara se captura sin ROS ni movimiento:

```bash
python3 scripts/capturar_colores.py
```

También acepta `--imagen FOTO.png`.

### Cadena completa de la pregunta 2 en modo articular (sin MoveIt)

Se usa `src/parcial_jetcobot/config/posiciones_fijas.articular.example.json`: postura de búsqueda `[20,-8,-21,-54,0,-22]`, ROI P1–P4 de 140×140 px centradas en las anclas calibradas, poses P1–P4 y depósitos por color en grados. Copiarla y confirmar cada pose solo después de probarla supervisada:

```bash
cp -n src/parcial_jetcobot/config/posiciones_fijas.articular.example.json config/posiciones_fijas.local.json
python3 scripts/preflight.py --config config/posiciones_fijas.local.json --real   # lista lo pendiente
```

Orden de arranque en el Jetson (una terminal por línea, mismo dominio):

```bash
python3 integraciones/sync_plan_p2.py                                    # driver único: /joint_states, medidas y pinza
ros2 launch parcial_jetcobot parcial.launch.py config_file:="$PWD/config/posiciones_fijas.local.json"
ros2 param set /driver_p2 habilitar_comandos true                       # solo con el brazo despejado
```

El lanzamiento sustituye al broker articular de prueba (`ros2 run arm_broker broker`): no ejecutar ambos. Los integrantes envían órdenes con `cliente_ordenes` o `transcriptor_voz` desde sus máquinas.

## 9 Archivos compartidos y privados

Sube fuentes, ejemplos y `avances/`. Las claves y configuraciones específicas van en variables de entorno o archivos `.local.json`, `.local.xml` y `config/equipo.env`, excluidos por Git. `build*`, `install*`, `log*`, cachés y respaldos también están excluidos. Los resultados nuevos se guardan con nombre propio; no sobrescribas los originales recibidos.

La documentación se concentra en este documento y el README principal. Los audios, registros y resultados del laboratorio se conservan en `avances/`.
