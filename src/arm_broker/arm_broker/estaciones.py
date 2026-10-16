""" Estaciones de trabajo del JetCobot: las 4 posiciones del tapete — fuente única de verdad """

""" Sobre el tapete hay un recuadro con CUATRO estaciones conocidas. Este archivo es el único
sitio que hay que tocar si cambian las esquinas o la cámara; tanto la visión como el movimiento
salen de aquí.

Por cada estación se guardan dos cosas:
  - 'roi'    : rectángulo (x1, y1, x2, y2) en PÍXELES de la imagen de referencia
               (ANCHO_REF × ALTO_REF). La cámara va montada en el brazo, así que el rectángulo
               solo vale con el brazo puesto en POSE_BUSQUEDA (ver poses.py), que es la pose
               desde la que se fotografiaron las cuatro estaciones.
  - 'agarre' : pose de pinza (6 ángulos, GRADOS) con la garra centrada y bajada sobre el cubo,
               lista para cerrar.

La numeración es la que se ve en la foto de la cámara:
    1 = arriba-izquierda      2 = arriba-derecha
    3 = abajo-izquierda       4 = abajo-derecha

Clave: las poses son POR ESTACIÓN, no por color. Cualquier cubo puede caer en cualquier
estación; el color lo resuelve la cámara (percepcion_camara) y aquí solo se elige la pose de la
estación donde se vio ese color. El número de estación es el CONTRATO entre visión y movimiento.

Si se cambia la cámara de sitio o la resolución, hay que volver a medir los rectángulos. Si la
resolución real difiere de ANCHO_REF×ALTO_REF, escalar_roi() los reajusta sola. """

# Resolución con la que se midieron los rectángulos (la cámara de la demo).
ANCHO_REF = 640
ALTO_REF = 480

ESTACIONES = {
    # estación: {'roi': (pixeles 640x480), 'agarre': (grados)}
    1: {'roi': (0,   0,   313, 243), 'agarre': [27, -48, -67,  29, 2, -6]},   # arriba-izq
    2: {'roi': (313, 0,   640, 243), 'agarre': [4,  -48, -71,  35, 0, -30]},  # arriba-der
    3: {'roi': (0,   243, 313, 480), 'agarre': [41, -16, -128, 58, 0, 1]},    # abajo-izq
    4: {'roi': (313, 243, 640, 480), 'agarre': [3,  -16, -128, 58, 0, -35]},  # abajo-der
}


def escalar_roi(rect, ancho, alto):
    """Ajusta un rectángulo de la resolución de referencia a la imagen real de la cámara, para
    que siga cuadrando aunque el driver entregue otra resolución."""
    x1, y1, x2, y2 = rect
    fx = ancho / float(ANCHO_REF)
    fy = alto / float(ALTO_REF)
    return (int(round(x1 * fx)), int(round(y1 * fy)),
            int(round(x2 * fx)), int(round(y2 * fy)))


def agarre(estacion):
    """Pose de agarre (grados) de una estación; None si la estación no existe."""
    datos = ESTACIONES.get(estacion)
    return list(datos['agarre']) if datos else None
