""" Poses de agarre y depósito del JetCobot — Ítem 2 (Pregunta 2) """

""" Todas las poses se declaran en GRADOS porque así las entrega el kit (send_angles de
pymycobot) y así se midieron sobre la mesa. El broker del RB-2 trabaja en RADIANES: por eso
todo goal move_arm se arma con a_radianes(). El broker es quien vuelve a GRADOS al publicar
/joint_states, que es lo que consume el driver sync_plan_nx.

Las CUATRO posiciones de la mesa son de cubos cualquiera: qué color hay en cada una lo decide
la cámara en vivo (percepcion_camara.py). Las cuatro ZONAS de depósito sí son fijas por color.

No hay MoveIt2, URDF/SRDF ni ros2_control en el repositorio: la "cinemática inversa" son estas
poses precalculadas más el troceado por paso articular de trozar(). """

import math

# 1. Pose de reposo
POSE_HOME = [0.0, 0.0, 0.0, 0.0, 0.0, -45.0]

# 1b. Pose de búsqueda: el brazo mira la mesa para que la cámara (montada en el brazo)
# vea los cuatro cubos. La percepción SOLO es válida con el brazo en esta pose.
POSE_BUSQUEDA = [-20.0, -16.0, -7.0, -61.0, 0.0, -24.0]

# 2. Las cuatro posiciones de cubo sobre la mesa (color-agnósticas)
POSICIONES_CUBO = {
    'pos1': [3.0, -19.0, -109.0, 31.0, 0.0, -45.0],
    'pos2': [41.0, -13.0, -126.0, 55.0, 0.0, -4.0],
    'pos3': [3.0, -51.0, -41.0, 0.0, 0.0, -45.0],
    'pos4': [25.0, -54.0, -39.0, 0.0, 0.0, -25.0],
}

# 3. Zonas de depósito fijas, una por color
DESTINOS = {
    'amarillo': [73.0, -56.0, -36.0, 0.0, -1.0, -33.0],
    'rojo': [87.0, -49.0, -48.0, 0.0, -1.0, -33.0],
    'verde': [106.0, -43.0, -55.0, 0.0, -1.0, -33.0],
    'azul': [123.0, -43.0, -55.0, 0.0, -1.0, -33.0],
}

# 4. Pinza (valores del kit: 100 abierta, 0 cerrada)
GRIPPER_ABIERTO = 100
GRIPPER_CERRADO = 0
GRIPPER_SPEED = 50

# 5. Conversión de unidades
def a_radianes(q_grados):
    """Convierte una pose [g1..g6] en grados a [q1..q6] en radianes."""
    return [math.radians(float(g)) for g in q_grados]

def a_grados(q_radianes):
    """Convierte una pose [q1..q6] en radianes a [g1..g6] en grados."""
    return [math.degrees(float(q)) for q in q_radianes]

# 6. Troceado por paso articular
def trozar(origen_rad, destino_rad, paso_max_rad):
    """Parte el tramo origen->destino (ambos en radianes) en metas intermedias.

    Devuelve la lista de metas SIN el origen y CON el destino final, de modo que cada salto
    entre metas consecutivas no supere paso_max_rad. Es el mismo camino recto en el espacio
    articular que ya interpola el broker; el troceado solo evita que el broker rechace el goal
    con causa 'paso'.
    """
    if paso_max_rad <= 0.0:
        raise ValueError('paso_max_rad debe ser positivo')
    if len(origen_rad) != 6 or len(destino_rad) != 6:
        raise ValueError('trozar requiere dos poses de 6 articulaciones')

    salto = max(abs(b - a) for a, b in zip(origen_rad, destino_rad))
    n = max(1, int(math.ceil(salto / paso_max_rad)))

    metas = []
    for k in range(1, n + 1):
        f = k / n
        metas.append([a + (b - a) * f for a, b in zip(origen_rad, destino_rad)])
    return metas

# 7. Búsqueda de poses por nombre
def pose_cubo(nombre):
    """Pose en grados de la posición de cubo 'pos1'..'pos4' (o None)."""
    return POSICIONES_CUBO.get(str(nombre).lower())

def pose_destino(color):
    """Pose en grados de la zona de depósito del color (o None)."""
    return DESTINOS.get(str(color).lower())
