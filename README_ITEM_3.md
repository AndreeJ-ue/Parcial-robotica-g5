# ÍTEM 3 — De la voz al texto (nodo `transcriptor_voz`)

Este documento explica el **Ítem 3** del Parcial JetCobot **a partir de los archivos que se
agregaron para que funcione**. En esta entrega, **lo propio del ítem 3 es la transcripción de
voz a texto** (`audio → texto`); el movimiento del brazo es el **ítem 2** y se detalla en
`PARA_COMPLETAR_EL_ITEM_2_Y_CERRAR_EL_ITEM_3.md`.

El ítem 3 se **antepone** al ítem 1: convierte el audio en una frase y se la entrega al servicio
`/interpretar_orden`. Aguas abajo, la decisión sigue el camino del ítem 1 y del ítem 2.

---

## 1. Archivos que se agregaron para completar el ítem 3

| Archivo (dónde vive) | Qué aporta al ítem 3 |
|---|---|
| `src/arm_broker/arm_broker/transcriptor_voz.py` | **El nodo**: toma un audio, lo pasa a texto con Google AI Studio y entrega la frase a `/interpretar_orden`. Si la nube falla, cae a **modo teclado**. |
| `src/arm_broker/arm_broker/voz_google.py` | **El único módulo HTTPS** hacia Google AI Studio (Gemini). Lee la clave de `GOOGLE_API_KEY`. |
| `src/arm_broker/arm_broker/orquestador.py` | **Puente mínimo** (parafraseado) que lleva la decisión hasta el broker. Sirve para cerrar la cadena; el ítem 2 completo se explica en su propio MD. |
| `herramientas/probar_transcripcion.py` | Prueba la transcripción **sin ROS 2** (confirmar clave, modelo y endpoint). |
| `herramientas/graficar_tiempos.py` | Dibuja el **desglose de tiempos** voz → movimiento (Parte C). |
| `evidencias/plantilla_ordenes.csv` | Plantilla de la **tabla de las 5 órdenes** de la demo. |
| `evidencias/transcripciones_cabecera.csv` | Cabecera del `transcripciones.csv` que escribe el nodo. |

> **Nota sobre el código:** los módulos están **reescritos/parafraseados** (nombres internos,
> comentarios y docstrings propios) pero **conservan el contrato de conexión**: los nombres de los
> parámetros del nodo, el formato de `transcripciones.csv`, el tópico `/orden_decidida`, el
> servicio `/interpretar_orden`, la variable `GOOGLE_API_KEY` y el endpoint de Gemini. Por eso
> siguen funcionando con las herramientas y con el broker.

> **Entry points:** `transcriptor_voz` y `orquestador` **ya están registrados** en
> `src/arm_broker/setup.py`. No hay que agregarlos a mano.

---

## 2. Qué pide el enunciado (y qué cubre esta entrega)

**Parte A — Transcripción** *(es lo propio de este ítem)*
- Nodo **`transcriptor_voz`**: toma audio (micrófono o archivo) y obtiene la transcripción **en
  español** consultando a **Google AI Studio**; el texto se entrega a `/interpretar_orden`.
- La **clave** se lee de **variable de entorno** (nunca en el código).
- **Su propio tiempo límite**: si la transcripción no llega o no hay internet → **modo texto por
  teclado** y se **informa**. El brazo nunca queda esperando.
- **Registrar** la transcripción junto con el audio original.

**Parte B — La cadena completa** *(depende del ítem 2)*
- Demo con **5 órdenes habladas**: una con **objeto que no está en la mesa** y una **no permitida**.
  Tabla: *lo que se dijo → lo que transcribió → la decisión → qué hizo el brazo*. La última
  columna es del **ítem 2**.

**Parte C — Dónde se va el tiempo** *(medición)*
- Medir desde que el operador **termina de hablar** hasta que el brazo **inicia el movimiento**,
  descomponiéndolo (captura, transcripción, decisión, cola, percepción, IK, planificación).
  **Tabla + figura** y las 2 preguntas numéricas.

**Entregables:** código del nodo · audios con su transcripción · tabla de las 5 órdenes · desglose
de tiempos con figura · **demo del modo texto con internet desconectado**.

---

## 3. Cómo funciona (el flujo)

```
audio (.wav) ──► transcriptor_voz ──HTTPS+clave──► Google AI Studio (nube)
                     │  timeout / sin internet
                     ├─► texto ──► /interpretar_orden (ítem 1) ──► decisión
                     └─► MODO TEXTO: el operador escribe por teclado ───┐
                                                                          ▼
                                                    /orden_decidida (ítem 2 sigue aguas abajo)
```

- **Por audio**: `transcriptor_voz` sube el `.wav` a Gemini con `GOOGLE_API_KEY` y publica la
  decisión en `/orden_decidida`.
- **Por texto**: si no hay internet / clave / timeout, el nodo usa `input()` por teclado.
- La **decisión la sigue tomando LAYA local** (no depende de internet).

Registro: `transcripciones.csv`
(`t_unix, ruta_audio, texto_transcrito, metodo, tiempo_transcripcion_s, tiempo_decision_s, t0, t1, t2, t3`).

---

## 4. Comandos exactos (y por qué)

### Paso A — Clave de Google AI Studio (solo variable de entorno)

1. Entra a <https://aistudio.google.com/apikey> con la cuenta del equipo.
2. **Create API key** → copia la clave (empieza tipo `AIza…`).

```powershell
# Windows (PowerShell)
$env:GOOGLE_API_KEY = "TU_CLAVE"
```
```bash
# Jetson (bash)
export GOOGLE_API_KEY="TU_CLAVE"
```

**Por qué así:** el código lee `os.environ['GOOGLE_API_KEY']`. Pegar la clave en un `.py` o
subirla al repo **descuenta puntos**.

> **Aviso de modelo:** el código trae por defecto `gemini-3.8-flash`
> (`voz_google.MODELO_POR_DEFECTO`), pero las guías usan `gemini-2.5-flash`. **Verifica el nombre
> real** y pásalo explícito:
> ```bash
> curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY" | head
> ```

### Paso B — Grabar el audio (en la Jetson/Raspberry)

```bash
arecord -l                                             # lista dispositivos, anota plughw:X,Y
arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 8 orden_01.wav
```

**Por qué 16 kHz mono:** es PCM simple y Gemini lo toma bien. Los `.wav` **no** están en el repo:
se generan en el examen. El nodo escribe `transcripciones.csv` en el **directorio desde donde se
lanza** (corre desde la raíz del workspace).

### Paso C — Probar la transcripción ANTES de tocar ROS 2

**Por qué:** confirmar clave, modelo y endpoint **sin ROS 2** ahorra depurar a ciegas.

```bash
cd ~/rb2_ws
export GOOGLE_API_KEY="TU_CLAVE"
python3 herramientas/probar_transcripcion.py orden_01.wav gemini-2.5-flash
# → Transcripción (... ms): 'agarra el cubo rojo'
```

Dependencias:

```bash
pip3 install requests --break-system-packages
pip3 install matplotlib --break-system-packages   # solo para graficar_tiempos.py
sudo apt install alsa-utils                        # provee arecord
```

### Paso D — Compilar y arrancar el nodo

El entry point **ya está registrado** en `src/arm_broker/setup.py`
(`transcriptor_voz = arm_broker.transcriptor_voz:main`). No hay que agregarlo.

```bash
cd ~/rb2_ws
colcon build --packages-select arm_broker --symlink-install
source install/setup.bash
```

**Por archivo (.wav):**

```bash
export GOOGLE_API_KEY="TU_CLAVE"
ros2 run arm_broker transcriptor_voz --ros-args \
  -p fuente:=archivo -p ruta_audio:=orden_01.wav \
  -p google_model:=gemini-2.5-flash \
  -p timeout_transcripcion_s:=5.0 -p n_ordenes:=1 \
  -p topico_decision:=orden_decidida
```

Cada audio nuevo:

```bash
ros2 run arm_broker transcriptor_voz --ros-args -p ruta_audio:=orden_02.wav -p n_ordenes:=1
```

**Por teclado (respaldo obligatorio):**

```bash
ros2 run arm_broker transcriptor_voz --ros-args -p fuente:=teclado -p n_ordenes:=5
```

**Fallback automático:** si Gemini falla (sin clave, sin internet, timeout), el nodo avisa y lee
`input()`.

### Paso E — Cerrar la cadena (contexto)

Para que la decisión llegue al brazo hace falta el **orquestador** y el **broker**. Este repo
incluye un **`orquestador.py` mínimo** (parafraseado) que se conecta al broker con **poses
placeholder**, suficiente para demostrar la cadena. El ítem 2 completo (cámara + poses reales +
pinza) se explica en `PARA_COMPLETAR_EL_ITEM_2_Y_CERRAR_EL_ITEM_3.md`.

```bash
ros2 run arm_broker broker                              # terminal 1 (RB-2; no se modifica)
ros2 run arm_broker interprete_ordenes --ros-args -p laya_url:=http://<IP_PC>:8000   # terminal 2
ros2 run arm_broker transcriptor_voz --ros-args -p ruta_audio:=orden_01.wav          # terminal 3
ros2 run arm_broker orquestador                                                      # terminal 4
```

### Paso F — Verificar el publicador único (regla dura)

```bash
python3 analisis/verificar_publicadores.py --salida evidencia/publicadores.txt
```

Debe salir **exactamente 1** publicador de `/joint_states` llamado `arm_broker`.

### Paso G — Demo SIN internet (entregable obligatorio)

Corta **solo** el internet, dejando viva la LAN con la PC de LAYA:

```bash
sudo iptables -A OUTPUT -d 0.0.0.0/0 -j DROP
sudo iptables -I OUTPUT -d <IP_PC_LAYA> -j ACCEPT      # la PC local sigue accesible

ping -c 2 8.8.8.8                            # debe FALLAR
curl -s http://<IP_PC_LAYA>:8000/health      # debe RESPONDER (LAN viva)

ros2 run arm_broker transcriptor_voz --ros-args -p ruta_audio:=orden_01.wav
#   → Gemini falla por DNS/timeout → loguea y pasa a MODO TEXTO POR TECLADO
#   → se escribe la orden a mano → decisión (LAYA local)

sudo iptables -D OUTPUT -d 0.0.0.0/0 -j DROP   # restaurar al terminar
```

**Por qué `iptables` con `ACCEPT` a la IP local:** si apagas `eth0/wlan0` pierdes también a LAYA.
Graba ese video: demuestra que **decisión y movimiento no dependen de internet**.

### Paso H — Desglose de tiempos y figura

Instantes: `t0` fin de habla · `t1` audio capturado · `t2` transcripción · `t3` decisión ·
`t4` goal aceptado · `t5` inicio real del movimiento.

Arma `etapas.csv` (mediana por etapa) y genera la figura:

```bash
python3 herramientas/graficar_tiempos.py etapas.csv --salida desglose_tiempos.png
```

---

## 5. Avisos / problemas comunes

- **Falta `GOOGLE_API_KEY`** → el nodo avisa y usa teclado (no es error fatal).
- **Modelo `404`** → `gemini-3.8-flash` puede no existir; usa `gemini-2.5-flash` (o lo que liste Gemini).
- **Siempre cae a texto** → sin internet o timeout bajo: sube `-p timeout_transcripcion_s:=8.0`.
- **`probar_transcripcion.py` debe vivir en `herramientas/`** (sube a `src/arm_broker` por ruta relativa).
- **CSV en el CWD** → lanza el nodo desde la raíz del workspace (`~/rb2_ws`).
- **Aislar internet mal** → no apagues `eth0/wlan0`; usa `iptables` con `ACCEPT` a la IP de tu PC.
- **Privacidad** → la clave solo por entorno; rota cualquier clave que haya quedado en el repo.

Ver `EVIDENCIAS_ITEM_3.md` para los entregables y el checklist.
