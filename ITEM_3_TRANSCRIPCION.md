# ÍTEM 3 — De la voz al texto (nodo `transcriptor_voz`)

Lo propio del ítem 3 es la **transcripción de voz a texto** (`audio → texto`). El nodo
`transcriptor_voz` toma un audio, lo pasa a texto en español con **Google AI Studio** (Gemini) y
entrega la frase al servicio `/interpretar_orden` del ítem 1. Si la nube no contesta o no hay
internet, **no falla**: avisa y pasa a **modo texto por teclado**. El movimiento del brazo es el
ítem 2 (`ITEM_2_BRAZO.md`); la cadena completa está en `DEMO_VOZ_A_BRAZO.md`.

---

## 1. Archivos del ítem 3

| Archivo | Qué aporta |
|---|---|
| `src/arm_broker/arm_broker/transcriptor_voz.py` | El nodo: toma un audio, lo pasa a texto con Google AI Studio y entrega la frase a `/interpretar_orden`. Si la nube falla, cae a modo teclado. |
| `src/arm_broker/arm_broker/voz_google.py` | Único módulo HTTPS hacia Google AI Studio (Gemini). Lee `GOOGLE_API_KEY`. |
| `herramientas/probar_transcripcion.py` | Prueba la transcripción **sin ROS 2**. |
| `herramientas/graficar_tiempos.py` | Dibuja el desglose de tiempos voz → movimiento. |
| `evidencias/plantilla_ordenes.csv` | Plantilla de la tabla de las 5 órdenes. |
| `evidencias/transcripciones_cabecera.csv` | Cabecera del `transcripciones.csv`. |

Entry points en `setup.py`: `transcriptor_voz` y `orquestador`.

## 2. Qué pide el enunciado

**Parte A — Transcripción** (lo propio del ítem 3)
- Nodo **`transcriptor_voz`**: toma audio (micrófono o archivo) y obtiene la transcripción en español
  consultando a **Google AI Studio**; el texto se entrega a `/interpretar_orden`.
- La **clave** se lee de **variable de entorno** (nunca en el código).
- **Su propio tiempo límite**: sin internet o timeout → **modo texto por teclado** y se informa.
- **Registrar** la transcripción junto con el audio original.

**Parte B — La cadena completa** (depende del ítem 2)
- Demo con **5 órdenes habladas**: una con **objeto que no está en la mesa** y una **no permitida**.
  Tabla: *lo que se dijo → lo que transcribió → la decisión → qué hizo el brazo*.

**Parte C — Dónde se va el tiempo** (medición)
- Medir desde que el operador **termina de hablar** hasta que el brazo **inicia el movimiento**,
  descomponiéndolo (captura, transcripción, decisión, cola, percepción, IK, planificación).

**Entregables:** código del nodo · audios con su transcripción · tabla de las 5 órdenes · desglose de
tiempos con figura · **demo del modo texto con internet desconectado**.

## 3. Cómo funciona

```
audio (.wav) ──► transcriptor_voz ──HTTPS+clave──► Google AI Studio (nube)
                     │  timeout / sin internet
                     ├─► texto ──► /interpretar_orden (ítem 1) ──► decisión
                     └─► MODO TEXTO: el operador escribe por teclado ───┐
                                                                         ▼
                                                   /orden_decidida (ítem 2 sigue aguas abajo)
```

**Registro:** `transcripciones.csv`
(`t_unix, ruta_audio, texto_transcrito, metodo, tiempo_transcripcion_s, tiempo_decision_s, t0, t1, t2, t3`).

---

## 4. Comandos exactos, paso a paso

### Entorno (en CADA terminal de la Jetson)
```bash
cd ~/rb2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=47                     # el que asigne el docente
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DISCOVERY_SERVER="<IP_DEL_ROBOT>:11811"
ros2 daemon stop; ros2 daemon start
```
**Qué hace:** carga ROS 2 + el paquete, fija dominio/middleware/descubrimiento y reinicia el daemon.

### Paso A — Clave de Google AI Studio (solo variable de entorno)
1. Entra a <https://aistudio.google.com/apikey> → **Create API key** → copia la clave (`AIza…`).
```powershell
# Windows (PowerShell)
$env:GOOGLE_API_KEY = "TU_CLAVE"
```
```bash
# Jetson (bash)
export GOOGLE_API_KEY="TU_CLAVE"
```
**Qué hace / por qué así:** el código lee `os.environ['GOOGLE_API_KEY']`. Pegar la clave en un `.py` o
subirla al repo **descuenta puntos**.

> **Aviso de modelo:** verifica el nombre real y pásalo explícito:
> ```bash
> curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY" | head
> ```
> Las guías usan `gemini-2.5-flash`.

### Paso B — Grabar el audio (Jetson/Raspberry)
```bash
arecord -l                                             # lista dispositivos, anota plughw:X,Y
arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 8 orden_01.wav
```
**Qué hace:** lista los dispositivos de captura y graba 8 s en **16 kHz mono PCM**, formato que Gemini
toma bien. Los `.wav` no están en el repo: se generan en el examen. El nodo escribe
`transcripciones.csv` en el directorio desde donde se lanza.

### Paso C — Probar la transcripción ANTES de tocar ROS 2
```bash
cd ~/rb2_ws
export GOOGLE_API_KEY="TU_CLAVE"
python3 herramientas/probar_transcripcion.py orden_01.wav gemini-2.5-flash
# → Transcripción (... ms): 'agarra el cubo rojo'
```
**Qué hace:** llama directamente a Google AI Studio sin ROS 2, para validar clave/modelo/audio.
Dependencias:
```bash
pip3 install requests --break-system-packages
pip3 install matplotlib --break-system-packages   # solo para graficar_tiempos.py
sudo apt install alsa-utils                        # provee arecord
```

### Paso D — Compilar y arrancar el nodo
```bash
cd ~/rb2_ws
colcon build --packages-select arm_broker --symlink-install
source install/setup.bash
```
**Qué hace:** compila el paquete y recarga el entorno.

**Por archivo (.wav):**
```bash
export GOOGLE_API_KEY="TU_CLAVE"
ros2 run arm_broker transcriptor_voz --ros-args \
  -p fuente:=archivo -p ruta_audio:=orden_01.wav \
  -p google_model:=gemini-2.5-flash \
  -p timeout_transcripcion_s:=5.0 -p n_ordenes:=1 \
  -p topico_decision:=orden_decidida
```
**Qué hace:** transcribe el `.wav`, llama `/interpretar_orden` y publica la decisión en
`/orden_decidida`. Cada audio nuevo:
```bash
ros2 run arm_broker transcriptor_voz --ros-args -p ruta_audio:=orden_02.wav -p n_ordenes:=1
```

**Por teclado (respaldo obligatorio):**
```bash
ros2 run arm_broker transcriptor_voz --ros-args -p fuente:=teclado -p n_ordenes:=5
```
**Qué hace:** no transcribe; lee frases por teclado. **Fallback automático:** si Gemini falla (sin
clave, sin internet, timeout), el nodo avisa y lee `input()`.

### Paso E — Demo SIN internet (entregable obligatorio)
Corta **solo** el internet, dejando viva la LAN con la PC de LAYA:
```bash
sudo iptables -A OUTPUT -d 0.0.0.0/0 -j DROP
sudo iptables -I OUTPUT -d <IP_PC_LAYA> -j ACCEPT      # la PC local sigue accesible

ping -c 2 8.8.8.8                            # debe FALLAR
curl -s http://<IP_PC_LAYA>:8000/health      # debe RESPONDER (LAN viva)

ros2 run arm_broker transcriptor_voz --ros-args -p ruta_audio:=orden_01.wav
#   → Gemini falla → loguea y pasa a MODO TEXTO POR TECLADO

sudo iptables -D OUTPUT -d 0.0.0.0/0 -j DROP   # restaurar al terminar
```
**Qué hace / por qué así:** bloquea la salida a internet pero **acepta** el tráfico a la PC de LAYA,
demostrando que **la decisión y el movimiento no dependen de internet**. No apagues `eth0/wlan0` o
perderías también a LAYA. Graba el video del modo texto.

### Paso F — Desglose de tiempos y figura
Instantes: `t0` fin de habla · `t1` audio capturado · `t2` transcripción · `t3` decisión · `t4` goal
aceptado · `t5` inicio real del movimiento.

```csv
etapa,mediana_s
Captura de audio,0.05
Transcripcion en la nube,0.90
Decision del modelo,0.42
Espera en la cola,1.10
Percepcion,0.08
Cinematica inversa,0.12
Planificacion,0.20
```
**Qué significa:** Captura = `t1-t0`; Transcripción = `t2-t1`; Decisión = `t3-t2`; Cola =
`wait_time_s`; Total voz→movimiento = `t5-t0`. Genera la figura:
```bash
python3 herramientas/graficar_tiempos.py etapas.csv --salida desglose_tiempos.png
```
**Qué hace:** dibuja el desglose por etapa (entregable).

---

## 5. Parámetros del nodo (`transcriptor_voz`)

| Parámetro | Ejemplo | Qué significa |
|---|---|---|
| `fuente` | `archivo` | De dónde sale la orden: `archivo` (`.wav`) o `teclado`. |
| `ruta_audio` | `orden_01.wav` | Audio a transcribir cuando `fuente=archivo`. |
| `google_model` | `gemini-2.5-flash` | Modelo de Google AI Studio. |
| `timeout_transcripcion_s` | `5.0` | **Su** tiempo límite; al vencer cae a texto por teclado. |
| `modo_texto_tras_fallo` | `true` | Permite el fallback automático a teclado. |
| `n_ordenes` | `1` | Cuántas órdenes procesa; `<=0` = indefinido. |
| `csv_transcripciones` | `transcripciones.csv` | Dónde registra cada transcripción. |
| `topico_decision` | `orden_decidida` | Tópico donde publica la decisión. |

## 6. Verificación y evidencias

```bash
python3 analisis/verificar_publicadores.py --salida evidencia/publicadores.txt
```
**Qué hace:** cuenta quién publica `/joint_states`. Debe salir **exactamente 1** publicador llamado
`arm_broker`.

| Evidencia | Cómo se genera |
|---|---|
| `transcripciones.csv` | Lo escribe `transcriptor_voz` (una fila por audio). |
| `orden_01.wav … orden_05.wav` | `arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 8 orden_0X.wav` |
| `ordenes_demo.csv` (5 órdenes) | Llenar `evidencias/plantilla_ordenes.csv` con la demo real. |
| `etapas.csv` | Mediana por etapa (formato arriba). |
| `desglose_tiempos.png` | `python3 herramientas/graficar_tiempos.py etapas.csv --salida desglose_tiempos.png` |
| Video del **modo texto sin internet** | Demo del Paso E. |
| `evidencia/publicadores.txt` | `verificar_publicadores.py --salida ...` |

**Tabla de las 5 órdenes (`ordenes_demo.csv`):** debe incluir **una con objeto que no está en la
mesa** y **una no permitida**. Criterio de acierto: resultado final esperado, **incluido el rechazo**
cuando corresponde.

**Las 2 preguntas numéricas (responde con TUS números):**
1. **¿Cuál es la etapa dominante?** — la de mayor mediana (suele ser la transcripción en la nube o la
   espera en la cola).
2. **Si hay que reducir a la mitad el tiempo voz→movimiento, ¿sobre qué etapa trabajas y qué dejas de
   obtener?** — atacar la transcripción (modelo de voz local) mejora el total pero pierdes calidad ASR
   multilingüe; atacar la cola (menor `tau`, prioridades agresivas) mejora lo urgente pero **empeora la
   equidad** de las prioridades bajas.

**Checklist:**
- [ ] `probar_transcripcion.py orden_01.wav gemini-2.5-flash` devuelve la frase.
- [ ] `transcriptor_voz` funciona por archivo y por teclado.
- [ ] Fallback a teclado verificado (sin clave / sin internet).
- [ ] `transcripciones.csv` con una fila por audio.
- [ ] `ordenes_demo.csv` (5 órdenes, incluida no permitida y objeto inexistente).
- [ ] `etapas.csv` + `desglose_tiempos.png` + respuestas a las 2 preguntas.
- [ ] Demo **sin internet** en modo texto, grabada en video.
- [ ] `verificar_publicadores.py` = exactamente 1 publicador `arm_broker`.

## 7. Problemas comunes
- **Falta `GOOGLE_API_KEY`** → el nodo avisa y usa teclado (no es error fatal).
- **Modelo `404`** → usa `gemini-2.5-flash` (o lo que liste Gemini).
- **Siempre cae a texto** → sin internet o timeout bajo: sube `-p timeout_transcripcion_s:=8.0`.
- **CSV en el CWD** → lanza el nodo desde la raíz del workspace (`~/rb2_ws`).
- **Aislar internet mal** → no apagues `eth0/wlan0`; usa `iptables` con `ACCEPT` a la IP de tu PC.
- **Privacidad** → la clave solo por entorno; rota cualquier clave que haya quedado en el repo.
