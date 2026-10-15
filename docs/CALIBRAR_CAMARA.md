# Calibrar la cámara del Ítem 2 (paso a paso)

La cámara va **montada en el brazo**, así que **solo ve bien la mesa cuando el brazo está en
`POSE_BUSQUEDA = [-20, -16, -7, -61, 0, -24]`**. Por eso:

1. Primero se pone el brazo en `POSE_BUSQUEDA`.
2. Después se calibran las **anclas de píxel** (`anclas_camara`), que son las coordenadas en la
   imagen 640×480 donde cae cada una de las 4 posiciones de cubo (`pos1..pos4`).
3. Esas anclas se pegan en el orquestador (o se dejan por defecto).

> Las anclas cambian si mueves la cámara, cambias de resolución o cambias la pose de búsqueda.
> Si algo de eso pasa, **vuelve a calibrar**.

---

## 0. Requisitos

- En la Jetson, con el workspace activado (ver `docs/EJECUTAR_ITEM_2.md`):
  ```bash
  cd ~/anchy
  source /opt/ros/humble/setup.bash
  source install/setup.bash
  ```
- **OpenCV** para Python:
  ```bash
  sudo apt install -y python3-opencv
  ```
- Para calibrar con el brazo moviéndose solo (`--mover-brazo`), tener corriendo el **broker** y el
  **driver** (ver `docs/EJECUTAR_ITEM_2.md`, terminales T1 y T2).

---

## 1. Poner el brazo en `POSE_BUSQUEDA`

Tienes dos formas:

- **Automática (recomendada):** el propio calibrador lo hace con `--mover-brazo` (manda el goal al
  broker). Salta al paso 2 con esa bandera.
- **Manual:** mueve el brazo a `POSE_BUSQUEDA = [-20, -16, -7, -61, 0, -24]` con el mando del kit y
  ejecuta el calibrador **sin** `--mover-brazo`.

---

## 2. Ejecutar el calibrador

Desde `~/anchy`:

```bash
# Automático: el calibrador manda el brazo a POSE_BUSQUEDA por el broker
python3 herramientas/calibrar_camara.py --mover-brazo --guardar foto_anclas.jpg

# Manual: tú ya dejaste el brazo en POSE_BUSQUEDA
python3 herramientas/calibrar_camara.py --guardar foto_anclas.jpg
```

Parámetros útiles:

| Parámetro | Para qué |
|---|---|
| `--indice N` | Elegir la cámara (0, 1, …). Por defecto autodetecta 0..3. |
| `--guardar RUTA` | Guarda una foto anotada (p. ej. `foto_anclas.jpg`). |
| `--mover-brazo` | Manda al broker un goal hasta `POSE_BUSQUEDA` antes de abrir la cámara. |
| `--paso 1.5` | Paso de troceado (radianes) para ir a `POSE_BUSQUEDA`. |

Se abre una ventana con la imagen en vivo.

---

## 3. Hacer clic en los 4 cubos

En la ventana:

- **Clic izquierdo** = fija el cubo actual. El orden es **`pos1` → `pos2` → `pos3` → `pos4`**.
  - `pos1..pos4` son las **cuatro esquinas fijas de la mesa** que corresponden a las poses
    `POSICIONES_CUBO` de `poses.py` (el color de cada una lo decide la cámara en vivo).
- **`r`** = reinicia los clics.
- **`s`** = guarda la foto anotada (si pasaste `--guardar`).
- **`q` o `ESC`** = termina y muestra la cadena de anclas.

Arriba de la imagen verás la pista de cuál toca (`clic: pos1`, `clic: pos2`, …).

---

## 4. Copiar el resultado

Al terminar imprime algo así:

```
-p anclas_camara:="['pos1=214,167','pos2=421,163','pos3=232,352','pos4=408,349']"
```

Copia ese texto completo (los valores serán los tuyos).

---

## 5. Dónde pegar las anclas

### Opción A — pasarlas al arrancar el orquestador (rápido, no cambia código)

```bash
ros2 run arm_broker orquestador --ros-args \
  -p gripper_habilitada:=true -p accion_pinza:=gripper_command \
  -p paso_orquestador_rad:=1.5 \
  -p usar_pose_busqueda:=true \
  -p anclas_camara:="['pos1=214,167','pos2=421,163','pos3=232,352','pos4=408,349']"
```

### Opción B — dejarlas por defecto

Pegar los mismos pares en el parámetro `anclas_camara` de
`src/arm_broker/arm_broker/orquestador.py` (y de `percepcion_camara.py` si quieres el mismo default).

---

## 6. Verificación rápida

1. Deja los 4 cubos en las esquinas.
2. Con el brazo en `POSE_BUSQUEDA`, lanza el orquestador con tus anclas.
3. Envía una orden por color (por ejemplo `agarra el cubo rojo`) desde `cliente_texto`.
4. En los logs del orquestador debe verse:
   - `🔎 POSE_BUSQUEDA: colocando la cámara frente a la mesa`
   - `🤖 Intento 1: rojo en posN → zona rojo`
   Si el color se asigna a la posición equivocada, revisa el `radio_ancla_px` (por defecto 70) o
   vuelve a calibrar: probablemente el clic no quedó sobre el centro del cubo.

---

## Solución de problemas

| Síntoma | Causa probable / solución |
|---|---|
| `falta OpenCV` | `sudo apt install -y python3-opencv`. |
| `no se encontró cámara` | Prueba `--indice 0`, `--indice 1`, …; revisa el cable USB. |
| `el broker no aparece` | El broker no está corriendo (T1) o falta `source install/setup.bash`. |
| El brazo no llega a `POSE_BUSQUEDA` | Usa `--mover-brazo` con broker+driver activos, o muévelo a mano. |
| El color cae en la posición equivocada | Recalibra con el brazo **exactamente** en `POSE_BUSQUEDA`; ajusta `radio_ancla_px`. |
