""" Planes de agarre y depósito del JetCobot — Ítem 2 (Pregunta 2) """

""" El tapete tiene CUATRO estaciones conocidas (ver estaciones.py) y en cada una puede haber
un cubo de cualquier color. Por eso la pose de agarre depende de DÓNDE se vio el color, no del
color. percepcion_camara resuelve el mapa {estación → color} y aquí se elige la pose de la
estación correspondiente.

Todos los ángulos van en GRADOS (es la convención del kit y así se midieron sobre la mesa). El
broker trabaja en RADIANES, así que cada goal move_arm se arma con a_radianes(); el broker es
quien vuelve a GRADOS al publicar /joint_states para el driver. No hay MoveIt2, URDF ni
ros2_control: la cinemática "inversa" son estas poses precalculadas más el troceado de trozar().

Antes de la demo conviene verificar límites, workspace y paso con herramientas/verificar_poses.py """

import math

from arm_broker import estaciones

# 1. Poses base (grados)
POSE_HOME = [0, 0, 0, 0, 0, -45]
# POSE_BUSQUEDA: vista global del tapete. Los rectángulos de estaciones.py se midieron desde
# aquí, así que la visión solo es válida con el brazo en esta pose.
POSE_BUSQUEDA = [20, -16, -7, -61, 0, -25]
# Pose de agarre por ESTACIÓN: cualquiera de los 4 cubos puede caer en cualquier estación.
AGARRES = {est: list(datos['agarre']) for est, datos in estaciones.ESTACIONES.items()}
# POSE_RECOGIDA (respaldo histórico): pose del centro. Solo se usa si no se resolvió la estación
# (p. ej. -p usar_estaciones:=false); con las 4 estaciones NO es una pose de agarre válida.
POSE_RECOGIDA = [18.28, -36.65, -76.37, 10.45, -0.26, -22.76]
POSE_REPARTO = [93.51, -4.04, -71.54, -12.83, -1.75, -36.29]

# 2. Zona de depósito por color (el destino "correcto" de cada objeto)
DESTINOS = {
    'amarillo': [65.12, -72.15, -8.87, -11.77, 5.18, -66.18],
    'rojo': [80.15, -45.35, -61.78, 12.39, 5.27, -51.24],
    'verde': [96.15, -35.15, -81.73, 23.37, 5.27, -36.56],
    'azul': [113.29, -35.15, -81.73, 23.37, 5.27, -18.63],
}

# 3. Pinza del kit (100 = abierta, 15 = cerrada; el driver usa esta escala 0..100)
GRIPPER_ABIERTO = 100
GRIPPER_CERRADO = 15
GRIPPER_SPEED = 50


# 4. Unidades
def a_radianes(q_grados):
    """Pose [g1..g6] en grados → [q1..q6] en radianes."""
    return [math.radians(float(g)) for g in q_grados]


def a_grados(q_radianes):
    """Pose [q1..q6] en radianes → [g1..g6] en grados."""
    return [math.degrees(float(q)) for q in q_radianes]


# 5. Troceado por salto articular
def trozar(origen_rad, destino_rad, paso_max_rad):
    """Parte el tramo origen→destino (radianes) en metas intermedias, sin incluir el origen y
    terminando exactamente en destino, para que ninguna meta consecutiva supere paso_max_rad.
    Es el mismo segmento recto que interpola el broker; el troceado solo evita que el broker
    rechace el goal con causa 'paso' (su paso_max por defecto es 1.2 rad)."""
    if origen_rad is None or destino_rad is None:
        raise ValueError('trozar necesita dos poses (no None)')
    if paso_max_rad is None or paso_max_rad <= 0.0:
        return [list(destino_rad)]
    if len(origen_rad) != 6 or len(destino_rad) != 6:
        raise ValueError('trozar requiere dos poses de 6 articulaciones')

    salto = max(abs(b - a) for a, b in zip(origen_rad, destino_rad))
    n = max(1, int(math.ceil(salto / paso_max_rad)))
    return [[a + (b - a) * (k / n) for a, b in zip(origen_rad, destino_rad)]
            for k in range(1, n + 1)]


# 6. Consulta de poses por nombre
def agarre(estacion):
    """Pose de agarre (grados) de una estación; cae a POSE_RECOGIDA si la estación es None."""
    return list(AGARRES.get(estacion, POSE_RECOGIDA))


def pose_destino(color):
    """Pose de depósito (grados) del color; None si no hay destino definido."""
    return DESTINOS.get(str(color).lower())


# 7. Planes: cada plan es una lista de pasos que el orquestador ejecuta en orden.
#    Paso de pinza: ('gripper', 'abrir'|'cerrar')
#    Paso de brazo : ('pose', etiqueta, [grados])
# El orquestador YA deja el brazo en POSE_BUSQUEDA antes de llamar a estos planes (para que la
# cámara confirme el color y la estación), por eso los planes no repiten ese primer tramo.

def secuencia_agarrar(estacion=None):
    """Agarrar: abre, baja a la estación, cierra y SUBE de vuelta a POSE_BUSQUEDA con el cubo.
    Terminar en búsqueda (no en home) permite encadenar un 'mover' sin volver a agarrar."""
    return [
        ('gripper', 'abrir'),
        ('pose', 'agarre', agarre(estacion)),
        ('gripper', 'cerrar'),
        ('pose', 'busqueda', POSE_BUSQUEDA),
    ]


def secuencia_soltar():
    """Soltar: abre la pinza donde esté el brazo, sin moverlo."""
    return [('gripper', 'abrir')]


def _tramo_transporte(color):
    """Transporte: desde POSE_BUSQUEDA hasta la zona del color y suelta (sin volver a home).
    Asume que el brazo ya está en POSE_BUSQUEDA (lo dejó secuencia_agarrar)."""
    pasos = [('pose', 'reparto', POSE_REPARTO)]
    destino = pose_destino(color)
    if destino:
        pasos.append(('pose', f'destino_{color}', destino))
    pasos.append(('gripper', 'abrir'))
    return pasos


def secuencia_transportar(color):
    """'mover' con el cubo ya en mano: solo completa el tramo y vuelve a home."""
    return _tramo_transporte(color) + [('pose', 'home', POSE_HOME)]


def secuencia_completa(color, estacion=None):
    """'mover' de cero: agarra en la estación + transporta al destino + vuelve a home."""
    return secuencia_agarrar(estacion) + _tramo_transporte(color) + [('pose', 'home', POSE_HOME)]
