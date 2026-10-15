# Qué archivos ya existían ANTES de los ítems 1 y 3

Este documento responde a: **¿qué había antes de implementar estos ítems?** Sirve para entender
que los ítems 1 y 3 **no parten de cero**: se apoyan en la etapa anterior del proyecto (**RB-2**,
"Reto Brazo 2"), que ya traía el brazo, el broker, la cinemática y las políticas de cola.

Resumen en una línea: **el RB-2 construyó el camino hasta el brazo; el ítem 1 le puso "cerebro
para entender la frase" y el ítem 3 le puso "orejas" (voz) por delante.**

---

## Baseline (existía antes)

### Paquete `arm_broker_interfaces` (interfaces ROS 2)

| Archivo | Qué era |
|---|---|
| `action/MoveArm.action` | La **acción** del brazo: `joint_positions` (radianes), `client_id`, `priority` (0..255, mayor = más urgente). |
| `msg/QueueState.msg` | **Telemetría** de la cola a 5 Hz (cola pendiente, ejecutando, contadores...). |
| `CMakeLists.txt` / `package.xml` | Build `ament_cmake`. |

### Paquete `arm_broker` (nodos y lógica)

| Archivo | Qué era |
|---|---|
| `broker.py` | El **broker**: servidor de la acción `move_arm`, cola de prioridad, **único publicador de `/joint_states`** y **único que manda al brazo**. Corazón del RB-2. **En esta carpeta está sin cambios.** |
| `fk.py` | **Cinemática directa** (tabla DH) + validaciones (`dentro_de_limites`, `dentro_del_workspace`, `paso_articular`). |
| `politicas.py` | **Políticas de cola**: `FIFO` y `prioridad` (con envejecimiento/aging). |
| `cliente.py` | Cliente de trazas para **cargar** el broker (RB-2). *No se copió aquí (es del bloque del ítem 2).* |
| `__init__.py`, `setup.py`, `setup.cfg`, `package.xml`, `resource/arm_broker` | El paquete y sus **entry points**. |
| `herramientas/generar_carga.py`, `simular_corrida.py`, `validar_rechazos.py`, `verificar_fk.py`, `verificar_poses.py` | Herramientas de la etapa RB-2. |
| `analisis/exportar_csv.py`, `metricas.py`, `verificar_publicadores.py`, etc. | Instrumentación de bags y métricas del broker. |
| `README.md`, `TERMINALES.md`, `PASOS.txt`, `carga.csv` | Documentación y traza de carga del RB-2. |

Todo esto **ya estaba** antes de los ítems 1 y 3. La regla del **publicador único** y el **broker**
son del RB-2, no de los ítems nuevos.

---

## Qué agregó el Ítem 1 (interpretación de frases)

| Archivo (nuevo) | Dónde va |
|---|---|
| `srv/InterpretarOrden.srv` | `arm_broker_interfaces/srv/` — se **agregó** la línea al `CMakeLists.txt`. |
| `interprete_ordenes.py` | `arm_broker/arm_broker/` — el nodo del servicio. |
| `cliente_laya.py` | `arm_broker/arm_broker/` — único módulo HTTP hacia LAYA. |
| `clasificador_palabras_clave.py` | `arm_broker/arm_broker/` — respaldo sin red. |
| `herramientas/probar_laya.py`, `medir_item1.py`, `frases_ejemplo.csv` | Herramientas del ítem 1. |

Entry point agregado: `interprete_ordenes = arm_broker.interprete_ordenes:main`.

El ítem 1 **no toca el brazo**: solo produce decisiones (y las publica en `/orden_decidida` para
que las consuma el orquestador).

---

## Qué agregó el Ítem 3 (voz → texto)

| Archivo (nuevo) | Dónde va |
|---|---|
| `transcriptor_voz.py` | `arm_broker/arm_broker/` — el nodo (audio → texto → `/interpretar_orden`). |
| `voz_google.py` | `arm_broker/arm_broker/` — módulo HTTP hacia Google AI Studio. |
| `herramientas/probar_transcripcion.py`, `graficar_tiempos.py` | Herramientas del ítem 3. |

Entry point agregado: `transcriptor_voz = arm_broker.transcriptor_voz:main`.

Además, para **cerrar la cadena** hasta el broker, esta entrega incluye el **`orquestador.py`** del
ítem 2 (parafraseado) con su entry point `orquestador = arm_broker.orquestador:main`: cámara +
poses + pinza + cola. Antes existía un `orquestador.py` mínimo con poses placeholder; ahora ese
mismo archivo es el orquestador completo. El detalle está en `README_ITEM_2.md` y
`COMANDOS_ITEM_2.md`.

---

## Tabla resumen: quién es de qué etapa

| Archivo / pieza | Etapa |
|---|---|
| `broker.py`, `fk.py`, `politicas.py`, `cliente.py` | Baseline RB-2 |
| `MoveArm.action`, `QueueState.msg` | Baseline RB-2 |
| `verificar_publicadores.py` | Baseline (regla que usan todos) |
| `InterpretarOrden.srv`, `interprete_ordenes.py`, `cliente_laya.py`, `clasificador_palabras_clave.py`, `probar_laya.py`, `medir_item1.py`, `frases_ejemplo.csv` | **Ítem 1** |
| `transcriptor_voz.py`, `voz_google.py`, `probar_transcripcion.py`, `graficar_tiempos.py` | **Ítem 3** |
| `orquestador.py` | **Ítem 2** (orquestador completo: cámara + poses + pinza + cola) |
| `percepcion_camara.py`, `poses.py`, `gripper.py`, `intentos.py`, `cliente_texto.py`, `pinza_pymycobot.py` | **Ítem 2** (fuera de esta carpeta) |

## Por qué importa saber esto

- Si ves la regla del **publicador único**, el **broker** o la **cola de prioridad**, eso viene del
  baseline: los ítems 1 y 3 **no deben** romperlo.
- El ítem 1 y el ítem 3 solo **producen decisiones**; el que **mueve** el brazo es el ítem 2.
  Mantener esa separación es lo que hace que la cadena sea segura.
- En esta carpeta, el **`broker.py` está intacto** (byte a byte); se parafrasearon **`fk.py` y
  `politicas.py`**, los módulos de los ítems 1 y 3 y el orquestador del ítem 2, conservando el
  contrato de conexión (los nombres que usa el broker quedan iguales).
