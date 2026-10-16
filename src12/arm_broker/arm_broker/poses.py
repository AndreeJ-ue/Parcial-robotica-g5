""" Poses fijas (IK precalculada) del JetCobot para el agarre — Pregunta 2 """

""" Sobre la mesa hay un espacio delimitado con CUATRO posiciones conocidas (las esquinas).
En cada posición puede haber un cubo de cualquier color, así que la pose de agarre no depende
del color sino de DÓNDE se vio ese color. La cámara (percepcion_camara) resuelve el mapa
{posición → color} y aquí se elige la pose de la posición correspondiente.

La tabla POSICIÓN→(ROI, pose de agarre) vive en zonas.py (fuente única de verdad); este módulo
solo arma los PLANES. Las poses están en GRADOS (la convención del script probado con el kit,
docs/agarrar_cubo_sin_rastreo.py) y se convierten a RADIANES para enviarlas al broker.
Antes de la demo hay que verificar que pasan límites, workspace y paso con
herramientas/verificar_poses.py """

import math

try:
    from arm_broker import zonas
except ImportError:                      # por si se ejecuta suelto desde la carpeta del paquete
    import zonas

# 1. Poses base (grados, convención del kit)
POSE_HOME = [0, 0, 0, 0, 0, -45]
# POSE_BUSQUEDA es la vista global del tapete; las ROIs de zonas.py se midieron desde aquí.
POSE_BUSQUEDA = list(zonas.POSE_BUSQUEDA)
# Pose de agarre por POSICIÓN (grados): RECOGIDAS[slot]. Cualquier color puede caer en cualquier slot.
RECOGIDAS = {slot: list(z['recogida']) for slot, z in zonas.ZONAS.items()}
# POSE_RECOGIDA (legacy): pose única del centro, solo se usa si no se pudo resolver la posición
# (p. ej. -p usar_zonas:=false). Con las 4 posiciones nuevas NO es una pose válida de agarre.
POSE_RECOGIDA = [18.28, -36.65, -76.37, 10.45, -0.26, -22.76]
POSE_REPARTO = [93.51, -4.04, -71.54, -12.83, -1.75, -36.29]

# 2. Zonas de depósito por color (la "zona correcta" de cada objeto)
DESTINOS = {
    'amarillo': [65.12, -72.15, -8.87, -11.77, 5.18, -66.18],
    'rojo': [80.15, -45.35, -61.78, 12.39, 5.27, -51.24],
    'verde': [96.15, -35.15, -81.73, 23.37, 5.27, -36.56],
    'azul': [113.29, -35.15, -81.73, 23.37, 5.27, -18.63],
}


def recogida(slot):
    """Pose de agarre (grados) de una posición; cae a POSE_RECOGIDA si el slot es None/desconocido."""
    return list(RECOGIDAS.get(slot, POSE_RECOGIDA))


def a_radianes(grados):
    """Convierte una pose de 6 ángulos de grados a radianes (para el broker)"""
    return [math.radians(v) for v in grados]


def escalonar(q_desde_rad, q_hasta_rad, paso_max_rad):
    """Trocea un movimiento en poses intermedias para que ningún salto articular entre metas
    consecutivas supere paso_max_rad (el broker revalida el paso al ejecutar, y si nos pasamos
    lo rechaza con causa 'paso'). Retorna la lista de metas intermedias, la última exactamente
    en q_hasta_rad."""
    if paso_max_rad is None or paso_max_rad <= 0:
        return [list(q_hasta_rad)]

    salto = max(abs(b - a) for a, b in zip(q_desde_rad, q_hasta_rad))
    if salto <= paso_max_rad:
        return [list(q_hasta_rad)]

    n = max(2, int(math.ceil(salto / paso_max_rad)))
    puntos = []
    for k in range(1, n + 1):
        f = k / n
        puntos.append([a + (b - a) * f for a, b in zip(q_desde_rad, q_hasta_rad)])
    return puntos


# 3. Las 3 acciones del orquestador: agarrar, soltar, mover (mover decide solo si ya
#    tiene el cubo en mano o si tiene que agarrarlo primero — ver orquestador_item2._atender)

def plan_agarrar(slot=None):
    """'agarrar': abre, baja a la recogida DE ESA POSICIÓN, cierra, y VUELVE a POSE_BUSQUEDA
    con el cubo en mano.

    El orquestador ya deja el brazo en POSE_BUSQUEDA (espacio de detección) antes de llamar a
    este plan (para que la cámara confirme el color y la posición), por eso no se repite ese
    primer tramo. Termina en búsqueda (no en home) para poder encadenar 'mover' sin volver a
    agarrar. `slot` es la posición (1..4) donde se vio el color pedido."""
    return [
        ('gripper', 'abrir'),
        ('pose', 'recogida', recogida(slot)),
        ('gripper', 'cerrar'),
        ('pose', 'busqueda', POSE_BUSQUEDA),
    ]


def plan_soltar():
    """'soltar': abre la pinza donde esté el brazo, sin moverlo."""
    return [('gripper', 'abrir')]


def _transportar(color):
    """Tramo de transporte: desde POSE_BUSQUEDA hasta la zona del color y suelta (sin volver).

    Asume que el brazo YA está en POSE_BUSQUEDA (lo deja ahí plan_agarrar, o ya estaba ahí
    por una 'agarrar' anterior). Si el color no tiene destino conocido, solo pasa por reparto."""
    pasos = [('pose', 'reparto', POSE_REPARTO)]
    destino = DESTINOS.get((color or '').lower())
    if destino:
        pasos.append(('pose', f'destino_{color}', destino))
    pasos.append(('gripper', 'abrir'))
    return pasos


def plan_transportar(color):
    """'mover' cuando YA se agarró antes (orquestador.cargando=True): solo lleva y vuelve a home."""
    return _transportar(color) + [('pose', 'home', POSE_HOME)]


def plan_pick_and_place(color, slot=None):
    """'mover' de cero (sin agarre previo): agarra en la posición `slot` + lleva a la zona + home."""
    return plan_agarrar(slot) + _transportar(color) + [('pose', 'home', POSE_HOME)]
