# Para completar el ÍTEM 2 y cerrar el ÍTEM 3 de punta a punta

> **Nota (histórica).** Este documento describía lo que faltaba cuando esta carpeta solo traía el
> ítem 1 y la parte de voz del ítem 3. **Ese trabajo ya está hecho**: el `orquestador.py` de la
> carpeta **es** ahora el orquestador completo del ítem 2 (cámara + poses + pinza + cola), y las
> piezas que aquí se listaban como "faltantes" ya están incluidas. Se deja tal cual, como registro
> del plan original; para el estado actual ver `README_ITEM_2.md` y `COMANDOS_ITEM_2.md`.

Esta carpeta entrega **el ítem 1 completo** y **el ítem 3 en su parte propia (voz → texto)**. El
**ítem 2** (el que realmente **mueve el brazo**) no se incluye aquí: en `src/` hay archivos
exclusivos del ítem 2 que **no** se copiaron para no mezclarlo.

Como el ítem 3 **necesariamente usa el ítem 2** para llegar al brazo, se incluyó un
**`orquestador.py` mínimo** que ya se conecta al broker con **poses placeholder**. Con eso la
cadena `audio → texto → decisión → goal al broker` **cierra**, pero el robot todavía no va al
objeto correcto (no hay cámara + poses reales + pinza).

Este documento dice **exactamente qué piezas faltan y qué pedirle a la IA** para terminarlas y
dejar el ítem 3 completo.

---

## 1. Qué hace hoy el `orquestador.py` incluido (y cuál es su límite)

El `orquestador.py` de esta carpeta:

1. escucha la decisión en `/orden_decidida` (la publica `transcriptor_voz`);
2. **rechaza antes de encolar** las órdenes `permitido=False` y las de objeto/color desconocido,
   dejando el motivo en `rechazos_orquestador.csv`;
3. escala la prioridad (`prioridad × 85` → uint8), **elige una pose de un mapa placeholder** y
   envía un **goal** `move_arm` al **broker**.

**Límite:** las poses del mapa (`mapa_poses`) son **inventadas**, no vienen de la cámara ni de la
cinemática inversa. Por eso el brazo se movería a una posición fija, no al objeto real.

---

## 2. Piezas del ÍTEM 2 que faltan (viven en `src/` y no se copiaron aquí)

| Archivo (en `src/arm_broker/arm_broker/`) | Qué debe hacer |
|---|---|
| `orquestador.py` | El orquestador **completo**: decisión → rechazo antes de encolar → **cámara** para confirmar color/objeto → **pose** real → goal `move_arm` → **pinza** → registrar intentos y error de FK. Es el que reemplazó al `orquestador.py` mínimo. |
| `percepcion_camara.py` | Detección de **color/objeto** por cámara (p. ej. máscara HSV) para saber dónde agarrar. |
| `poses.py` | **Poses de agarre** (en grados, convención del kit) + `a_radianes()`; hoy la "IK" son poses precalculadas. |
| `gripper.py` | Envoltura de la **pinza**. |
| `intentos.py` | Registro de **intentos** y del **error de cinemática (FK)**. |
| `cliente_texto.py` | Cliente de frases por teclado (para pruebas del ítem 2). |
| `pinza_pymycobot.py` | Control directo de pinza del kit. |
| `cliente.py` | Cliente de trazas para **cargar** el broker (RB-2). |

> El **broker** (`broker.py`) está **sin cambios**; `fk.py` y `politicas.py` **sí** están en esta
> carpeta (parafraseados, con el contrato intacto): son la base sobre la que se apoya el ítem 2.

---

## 3. Qué pedirle a la IA (prompt listo para copiar)

> Pídele que **reconstruya el ítem 2 sin tocar el broker** y que respete las reglas duras. Un
> prompt que funciona:

```text
Contexto: proyecto ROS 2 Humble para el brazo JetCobot (parcial). Ya existe el paquete
`arm_broker` con:
  - `broker.py`  (NO se puede modificar): servidor de la acción `move_arm`, única cola de
    prioridad y ÚNICO publicador de /joint_states.
  - `fk.py`, `politicas.py` (base; parafraseados, conservan los nombres que usa el broker).
  - `interprete_ordenes.py` (ítem 1): servicio /interpretar_orden → decisión tipada.
  - `transcriptor_voz.py` (ítem 3): audio → texto → /interpretar_orden y publica la decisión
    en /orden_decidida (JSON con frase, accion, objeto, color, prioridad, permitido, motivo,
    fuente, degradada, t3).
  - `orquestador.py`: puente MÍNIMO que ya envía goals `move_arm` al broker, pero con poses
    placeholder.

Necesito COMPLETAR EL ÍTEM 2 (mover el brazo de verdad) respetando esto:
  1. Exactamente UN publicador de /joint_states: el broker. El orquestador NUNCA publica
     /joint_states; solo envía goals `move_arm`.
  2. Rechazar ANTES de encolar las órdenes permitido=False (con causa y motivo en CSV).
  3. Interno en RADIANES; /joint_states sale en GRADOS (lo hace el broker). No cambiar eso.
  4. Claves de API solo por variable de entorno.

Créame/ajústame estos archivos en `arm_broker/arm_broker/`:
  - `orquestador.py`: orquestador completo (sustituyó al mínimo). Suscripción a
    /orden_decidida, rechazo previo, uso de `percepcion_camara` para confirmar color, elección
    de pose con `poses.py`, envío de goal `move_arm` al broker (client_id, priority = prioridad
    escalada), comando de pinza con `gripper.py` (con flag `gripper_habilitada`), y registro de
    intentos/error FK con `intentos.py`.
  - `percepcion_camara.py`: detección de color/objeto por cámara.
  - `poses.py`: poses de agarre en GRADOS + `a_radianes()`; documenta que hoy no hay MoveIt2.
  - `gripper.py`, `intentos.py`, `cliente_texto.py`, `pinza_pymycobot.py`.
  - Registra los entry points nuevos en `setup.py`.

Reglas y parámetros que deben respetarse:
  - Parámetros del broker: `-p tau_envejecimiento_s:=12.0`, `-p paso_max_rad:=1.6`,
    `-p duracion_movimiento_s:=5.0`, `-p pasos_interpolacion:=1`.
  - El orquestador trocea movimientos largos; si su `paso_max_rad` es menor que el del broker,
    el broker rechaza con causa `paso`.
  - El driver del kit NO expone acción de pinza: `gripper_command` no responde. Deja
    `-p gripper_habilitada:=false` como opción.
  - NO hay MoveIt2, URDF/SRDF ni ros2_control en el repo: la "IK" son poses precalculadas.
  - NO lanzar `joint_state_publisher`.

Entrégame los archivos completos y un MD corto con: cómo compilar, en qué orden arrancar los
nodos y cómo verificar que hay un solo publicador de /joint_states.
```

---

## 4. Cómo cerrar el ítem 3 una vez esté el ítem 2

1. Copia los archivos nuevos a `src/arm_broker/arm_broker/` (o pídele a la IA que parta de esta
   misma carpeta).
2. Compila: `colcon build --packages-select arm_broker_interfaces arm_broker --symlink-install`.
3. Arranca, en este orden: `broker` → (driver `sync_plan_nx`) → `interprete_ordenes` →
   `transcriptor_voz` → `orquestador`.
4. Repite la demo de las 5 órdenes de `README_ITEM_3.md` (una con objeto inexistente y una no
   permitida) y completa la columna **"qué hizo el brazo"**.
5. Verifica la regla dura: `python3 analisis/verificar_publicadores.py` → **1** publicador
   `arm_broker`.

Con eso, el ítem 3 queda **completo**: `audio → texto → decisión → cola → brazo`.

---

## 5. Referencias del repo (para el ítem 2 a fondo)

- `docs/ITEM_2.md` y `docs/ITEM_2_EVIDENCIAS.md`.
- `PASOS/PASOS_ITEM_2.md`.
- `item2/` (carpeta-fuente con el código y su guía de copiado).
- `moveit2/` (ruta alternativa con planificador MoveIt2; **no aplicada a `src/`**).
- `ARQUITECTURA.md` §5.8–5.12 y §9.2.
