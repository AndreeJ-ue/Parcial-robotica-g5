""" Zonas (las 4 posiciones) del espacio delimitado del JetCobot — fuente única de verdad """

""" Aquí vive TODO lo que define dónde está cada posición y cómo se agarra. Es el único
archivo que hay que tocar si cambian las 4 esquinas.

Cada posición (slot) tiene:
  - 'roi'      : rectángulo (x1, y1, x2, y2) en PÍXELES de la imagen de REFERENCIA
                 (ANCHO_REF x ALTO_REF). La cámara mira el tapete desde POSE_BUSQUEDA.
  - 'recogida' : pose de agarre en GRADOS (6 ángulos). Es la pose con la pinza
                 centrada y bajada sobre el cubo, lista para cerrar.

Numeración (tal como se ve en la imagen de la cámara):
    1 = arriba-izquierda     2 = arriba-derecha
    3 = abajo-izquierda      4 = abajo-derecha

IMPORTANTE: las poses son POR POSICIÓN, no por color. Cualquier cubo puede estar en
cualquier posición; el color se resuelve con la cámara y aquí solo se elige la pose de
la posición donde se vio ese color. El número de slot es el CONTRATO entre la parte de
visión (percepcion_camara) y la de movimiento (poses/orquestador).

Si algún día cambias la cámara de sitio o la resolución, vuelve a medir las ROIs. Si la
resolución real difiere de ANCHO_REF/ALTO_REF, se reescalan solas con escalar_roi(). """

# Resolución de referencia con la que se midieron las ROIs (la cámara de la demo).
ANCHO_REF = 640
ALTO_REF = 480

# Pose de búsqueda: vista global del tapete (con el brazo fuera del encuadre) para que la
# cámara vea las 4 posiciones. En GRADOS. La ROIs se midieron con la cámara aquí.
POSE_BUSQUEDA = [20, -16, -7, -61, 0, -25]

ZONAS = {
    # slot: {roi (pixeles 640x480), recogida (grados)}
    1: {'roi': (0,   0,   313, 243), 'recogida': [27, -48, -67,  29, 2, -6]},  # arriba-izq
    2: {'roi': (313, 0,   640, 243), 'recogida': [4,  -48, -71,  35, 0, -30]},  # arriba-der
    3: {'roi': (0,   243, 313, 480), 'recogida': [41, -16, -128, 58, 0, 1]},  # abajo-izq
    4: {'roi': (313, 243, 640, 480), 'recogida': [3,  -16, -128, 58, 0, -35]},  # abajo-der
}


def escalar_roi(roi, ancho, alto):
    """Reescala un ROI de la resolución de referencia a la imagen real que llega de la cámara.
    Así, si usb_cam entrega otra resolución, los rectángulos siguen cuadrando."""
    x1, y1, x2, y2 = roi
    sx = ancho / float(ANCHO_REF)
    sy = alto / float(ALTO_REF)
    return (int(round(x1 * sx)), int(round(y1 * sy)),
            int(round(x2 * sx)), int(round(y2 * sy)))


def recogida(slot):
    """Pose de agarre (grados) de una posición; None si el slot no existe."""
    z = ZONAS.get(slot)
    return list(z['recogida']) if z else None
