# Carpeta `anchy` — Ítems 1, 2 y 3 del Parcial JetCobot

Esta carpeta reúne **lo necesario para los ítems 1, 2 y 3** del Parcial Gran Reto JetCobot,
explicado de forma fácil de entender: el código, las herramientas para probarlo y medirlo, lo
de análisis, y documentos que cuentan **qué pide cada ítem, cómo funciona, qué comandos ejecutar
exactamente y por qué**.

- **Ítem 1** → completo (interpretar la frase → decisión tipada).
- **Ítem 2** → implementado en **`orquestador.py`** (+ `poses.py`, `percepcion_camara.py`,
  `gripper.py`, `intentos.py`, `cliente_texto.py`): mueve el brazo de verdad con cámara + poses +
  pinza, sin tocar el broker. Ver `README_ITEM_2.md` y `COMANDOS_ITEM_2.md`. El documento
  `PARA_COMPLETAR_EL_ITEM_2_Y_CERRAR_EL_ITEM_3.md` queda como guía histórica de lo que faltaba.
- **Ítem 3** → su parte propia es la **transcripción de voz a texto**; el `orquestador.py` (ítem 2)
  cierra la cadena hasta el broker.

> Esta carpeta es una **copia autocontenida + explicación**. La **fuente de verdad** del proyecto
> sigue siendo `src/` del repositorio y el enunciado `Parcial_Gran_Reto_JetCobot.docx`. Si algo
> difiere, manda el `src/`.

> **El `broker.py` está tal cual** (no se modificó; es byte a byte el de `src/`). **Todo lo demás
> con texto propio fue parafraseado**: los módulos de los ítems 1, 2 y 3, el `orquestador.py` del
> ítem 2 y también **`fk.py` y `politicas.py`** (comentarios, docstrings y nombres internos). Todos
> **conservan el contrato de conexión** (servicio, tópicos, parámetros, CSV y los nombres que usa
> el broker), así que siguen funcionando igual.

---

## Orden de lectura

1. `00_COMO_FUNCIONA_LA_CADENA.md` — el panorama: los 3 ítems y cómo se conectan.
2. `01_QUE_HABIA_ANTES.md` — qué archivos ya existían **antes** de los ítems 1 y 3.
3. `README_ITEM_1.md` — **ítem 1**: qué pide, los archivos que se agregaron, comandos + por qué.
4. `README_ITEM_3.md` — **ítem 3**: la transcripción (audio → texto), comandos + por qué.
5. `README_ITEM_2.md` — **ítem 2**: mover el brazo (cámara + poses + pinza + cola del broker).
6. `COMANDOS_ITEM_2.md` — **ítem 2**: todos los comandos por terminal (FIFO y prioridad), explicados.
7. `COMANDOS_RAPIDOS.md` — chuleta de comandos (grupo 5, dominio 47, driver `jetcobot_driver`).
8. `docs/` — **paso a paso de ejecución**: `EJECUTAR_ITEM_2.md` y `CALIBRAR_CAMARA.md`.
9. `PARA_COMPLETAR_EL_ITEM_2_Y_CERRAR_EL_ITEM_3.md` — guía histórica de lo que faltaba del ítem 2.
10. `EVIDENCIAS_ITEM_1.md` y `EVIDENCIAS_ITEM_3.md` — entregables y checklist de cada ítem.

---

## Mapa de la carpeta

```
anchy/
├── README.md                                      ← este archivo (índice y reglas)
├── 00_COMO_FUNCIONA_LA_CADENA.md                  ← los 3 ítems y la cadena completa
├── 01_QUE_HABIA_ANTES.md                          ← baseline previo (RB-2) a los ítems 1 y 3
├── README_ITEM_1.md                               ← ítem 1: qué pide, archivos, comandos + por qué
├── README_ITEM_3.md                               ← ítem 3: transcripción de voz a texto
├── README_ITEM_2.md                               ← ítem 2: brazo (cámara + poses + pinza + cola)
├── COMANDOS_ITEM_2.md                             ← ítem 2: comandos por terminal (FIFO/prioridad)
├── COMANDOS_RAPIDOS.md                            ← chuleta de comandos (grupo 5, dominio 47)
├── docs/                                          ← paso a paso de ejecución (ítem 2)
│   ├── EJECUTAR_ITEM_2.md                         ← entorno + nodos + calibrar + órdenes
│   └── CALIBRAR_CAMARA.md                         ← calibrar las anclas de la cámara
├── PARA_COMPLETAR_EL_ITEM_2_Y_CERRAR_EL_ITEM_3.md ← guía histórica de lo que faltaba del ítem 2
├── EVIDENCIAS_ITEM_1.md                           ← entregables, comandos, checklist (ítem 1)
├── EVIDENCIAS_ITEM_3.md                           ← entregables, comandos, checklist (ítem 3)
│
├── src/                                           ← espejo de `src/` SIN lo exclusivo del ítem 2
│   ├── arm_broker/
│   │   ├── arm_broker/
│   │   │   ├── __init__.py
│   │   │   ├── broker.py                        (RB-2, SIN CAMBIOS: único publicador de /joint_states)
│   │   │   ├── fk.py                            (RB-2, parafraseado: base del broker)
│   │   │   ├── politicas.py                     (RB-2, parafraseado: base del broker)
│   │   │   ├── interprete_ordenes.py            (ítem 1: el nodo)
│   │   │   ├── cliente_laya.py                  (ítem 1: HTTP hacia LAYA)
│   │   │   ├── clasificador_palabras_clave.py   (ítem 1: respaldo sin red)
│   │   │   ├── transcriptor_voz.py              (ítem 3: el nodo, audio → texto)
│   │   │   ├── voz_google.py                    (ítem 3: HTTP hacia Google)
│   │   │   ├── orquestador.py                   (ítem 2: orquestador completo: cámara+poses+pinza)
│   │   │   ├── poses.py                         (ítem 2: poses en grados + troceado)
│   │   │   ├── percepcion_camara.py             (ítem 2: color → posición por cámara)
│   │   │   ├── gripper.py                       (ítem 2: pinza, vía acción gripper_command)
│   │   │   ├── pinza_pymycobot.py               (ítem 2: pinza por puerto serie, respaldo)
│   │   │   ├── intentos.py                      (ítem 2: intentos + error de FK)
│   │   │   └── cliente_texto.py                 (ítem 2: frases por teclado para pruebas)
│   │   ├── setup.py                             (entry points: broker, interprete_ordenes,
│   │   │                                          transcriptor_voz, orquestador, cliente_texto)
│   │   ├── setup.cfg / package.xml
│   │   └── resource/arm_broker
│   └── arm_broker_interfaces/
│       ├── action/MoveArm.action                (RB-2: la acción del brazo)
│       ├── msg/QueueState.msg                   (RB-2: telemetría de la cola)
│       ├── srv/InterpretarOrden.srv             (ítem 1: definición del servicio)
│       ├── CMakeLists.txt / package.xml
│
├── herramientas/                                  ← scripts para probar/medir (se corren a mano)
│   ├── probar_laya.py                               (ítem 1)
│   ├── medir_item1.py                               (ítem 1)
│   ├── frases_ejemplo.csv                           (ítem 1)
│   ├── probar_transcripcion.py                      (ítem 3)
│   ├── graficar_tiempos.py                          (ítem 3)
│   └── calibrar_camara.py                           (ítem 2: extraer anclas de la cámara)
│
├── analisis/
│   └── verificar_publicadores.py                    (regla dura: un solo publicador de /joint_states)
│
└── evidencias/                                      ← plantillas vacías para llenar en la demo
    ├── frases_50.csv                                (50 frases oficiales del docente)
    ├── plantilla_ordenes.csv                        (tabla de las 5 órdenes del ítem 3)
    └── transcripciones_cabecera.csv                 (cabecera de transcripciones.csv)
```

---

## Qué es cada carpeta

- **`src/`** — es el **espejo de los paquetes ROS 2 `arm_broker` y `arm_broker_interfaces`**, con
  **todo menos lo exclusivo del ítem 2**. En el repo real se compila con `colcon build`. El
  **broker** (`broker.py`) está **sin cambios** (byte a byte); `fk.py`, `politicas.py`, los
  módulos de los ítems 1 y 3 y el `orquestador.py` mínimo están **parafraseados** (conservando
  el contrato de conexión).
- **`herramientas/`** — scripts de **prueba y medición** que se corren a mano (varios **sin ROS 2**).
  Son los que producen las evidencias.
- **`analisis/`** — instrumentación. Para los ítems 1 y 3 solo hace falta
  `verificar_publicadores.py` (la regla dura del publicador único de `/joint_states`).
- **`evidencias/`** — plantillas vacías (frases, tabla de órdenes, cabecera del CSV).

**Por qué están juntos así:** los scripts de `herramientas/` buscan el paquete en
`../src/arm_broker` (dos niveles arriba del propio archivo). Al tener `anchy/herramientas/` al
lado de `anchy/src/`, los imports funcionan **sin tocar nada**.

> En la Jetson, los comandos se escriben desde la **raíz del workspace** (por ejemplo `~/rb2_ws`);
> en esta carpeta el equivalente es `anchy/`. Los comandos de los MDs usan `~/rb2_ws` porque es
> donde de verdad se compila y se corre.

---

## Reglas duras (romperlas anula puntaje)

1. **Exactamente UN publicador de `/joint_states`**: el nodo `arm_broker`. Nunca agregar otro
   (ni `joint_state_publisher`). Se verifica con `analisis/verificar_publicadores.py`.
2. **Solo el worker del broker manda al brazo.** El intérprete, el transcriptor y el orquestador
   mínimo solo **envían goals**; jamás publican `/joint_states`.
3. **Claves de API solo por variable de entorno** (`LAYA_API_KEY`, `GOOGLE_API_KEY`). Nunca dentro
   del código ni en el repo.
4. **Trampa de unidades:** lo interno va en **radianes**; `/joint_states` sale en **grados** (lo
   convierte el broker al publicar). No "corregir" ninguno de los dos lados.

---

## Requisitos por dispositivo

| Dispositivo | Qué corre aquí (ítems 1 y 3) |
|---|---|
| **PC Windows** | `laya-serve` (la decisión tipada). **No** necesita internet. |
| **Jetson (ROS 2 Humble)** | `interprete_ordenes` (ítem 1), `transcriptor_voz` (ítem 3), `orquestador` (puente) y `broker`; `colcon build`; `medir_item1.py`. |
| **Internet (nube)** | **Google AI Studio**: solo la transcripción de audio del ítem 3. |
| **PC cualquiera sin ROS** | `probar_laya.py` y `probar_transcripcion.py` (usan `requests`, no ROS). |
