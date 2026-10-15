""" Cinemática directa del JetCobot — Ítem 1 del Reto 2

Todas las cuentas se hacen a mano (listas y `math`) para que el paquete ROS 2 no
necesite NumPy.
"""

import math

# 1. Nombres de las seis articulaciones, en el mismo orden que el driver del kit
JOINT_NAMES = [
    '1_Joint',
    '2_Joint',
    '3_Joint',
    '4_Joint',
    '5_Joint',
    '6_Joint',
]

# 2. Tabla Denavit-Hartenberg (una fila por articulación)

# Tabla original:
#
# i     theta         d [mm]    a [mm]    alpha
# 1     q1            134.75       0       +90°
# 2     q2 - 90°        0       -110        0°
# 3     q3              0        -96        0°
# 4     q4 - 90°       63.4        0       +90°
# 5     q5 + 90°      75.55        0       -90°
# 6     q6             50          0        0°
#
# Cada tupla se guarda en este orden: alpha, a, d, offset_theta
DH = [
    ( math.pi / 2,    0.0, 134.75,           0.0),   # J1
    (         0.0, -110.0,   0.00, -math.pi / 2),    # J2
    (         0.0,  -96.0,   0.00,           0.0),   # J3
    ( math.pi / 2,    0.0,  63.40, -math.pi / 2),    # J4
    (-math.pi / 2,    0.0,  75.55,  math.pi / 2),    # J5
    (         0.0,    0.0,  50.00,           0.0),   # J6
]

# 3. Tope de cada articulación (todas las columnas en radianes)
JOINT_LIMITS = [
    (-2.93, 2.93),
    (-2.36, 2.36),
    (-2.53, 2.53),
    (-2.58, 2.58),
    (-2.93, 2.93),
    (-3.14, 3.14),
]

# 4. Filtro sencillo de alcance del efector, en milímetros desde la base
# Es el filtro geométrico que usa el broker.
ALCANCE_MIN_MM = 80.0
ALCANCE_MAX_MM = 480.0

# 5. Matriz homogénea A_i de una articulación (DH estándar)
def _matriz_dh(alpha, a, d, theta):
    """Se arma la matriz A_i de una articulación como
    A_i = Rot_z(theta) · Trans_z(d) · Trans_x(a) · Rot_x(alpha)

    Parámetros: alpha -> giro entre z(i-1) y z(i) alrededor de x(i), en rad
                a     -> distancia entre ejes z medida sobre x(i), en mm
                d     -> desplazamiento sobre z(i-1), en mm
                theta -> ángulo articular total, en rad
    Devuelve la matriz homogénea 4x4 como lista de listas.
    """
    ca = math.cos(alpha)
    sa = math.sin(alpha)
    ct = math.cos(theta)
    st = math.sin(theta)

    return [
        [ct, -st * ca,  st * sa, a * ct],
        [st,  ct * ca, -ct * sa, a * st],
        [0.0,       sa,       ca,      d],
        [0.0,      0.0,      0.0,    1.0],
    ]

# 6. Producto de matrices 4x4
def _multiplicar(A, B):
    """Producto de dos matrices 4x4.
    Se resuelve a mano para no depender de NumPy dentro del paquete ROS 2.
    """
    return [
        [
            sum(A[i][k] * B[k][j] for k in range(4))
            for j in range(4)
        ]
        for i in range(4)
    ]

# 7. Cinemática directa: matriz completa T_0_6
def fk_matriz(q):
    """Matriz homogénea T_0_6, desde la base hasta el efector.

    q es la lista o tupla de 6 ángulos articulares en radianes.
    Se calcula como T_0_6 = A1 · A2 · A3 · A4 · A5 · A6 y se devuelve la
    matriz homogénea 4x4.
    """
    if len(q) != 6:
        raise ValueError(
            f'fk_matriz(q) requiere 6 articulaciones; solo se recibieron {len(q)}'
        )

    # Se parte de la identidad y se va acumulando cada A_i
    T = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]

    # Se recorre cada fila DH junto al ángulo articular que le corresponde
    for (alpha, a, d, offset), angulo in zip(DH, q):
        angulo_dh = angulo + offset      # El ángulo de DH ya incluye el offset geométrico
        A_i = _matriz_dh(alpha, a, d, angulo_dh)  # Matriz individual A_1
        T = _multiplicar(T, A_i)         # T = A1, luego A1*A2, luego A1*A2*A3, ...

    return T

# 8. Cinemática directa: solo la posición XYZ
def fk(q):
    """Posición cartesiana (x, y, z) del efector final.

    Entrada: q = [q1, q2, q3, q4, q5, q6] en radianes
    Salida:  (x, y, z) en milímetros
    La posición sale de la última columna de T_0_6:
        |R00 R01 R02 x|
        |R10 R11 R12 y|
    T = |R20 R21 R22 z|
        | 0   0   0  1|
    """
    T = fk_matriz(q)

    x = T[0][3]
    y = T[1][3]
    z = T[2][3]

    return x, y, z

# 9. Validación de límites articulares
def dentro_de_limites(q):
    """Comprueba que las seis articulaciones estén dentro de sus límites.
    Devuelve (ok, motivo): motivo vacío cuando ok es True.
    """
    if len(q) != 6:
        return False, f'se esperaban 6 ángulos, llegaron {len(q)}'

    for i, (valor, (lo, hi)) in enumerate(zip(q, JOINT_LIMITS)):
        if not lo <= valor <= hi:
            return (
                False,
                f'{JOINT_NAMES[i]} fuera de rango: '
                f'{valor:.3f} rad, límite [{lo}, {hi}]'
            )

    return True, ''

# 10. Validación simple del workspace
def dentro_del_workspace(q):
    """Filtro básico de workspace sobre la posición que calcula la FK.

    Se toma r = sqrt(x² + y² + z²) y se rechaza el punto si r supera el alcance
    máximo, si queda por debajo del alcance mínimo o si z < 0.
    """
    x, y, z = fk(q)
    r = math.sqrt(x * x + y * y + z * z)

    if r > ALCANCE_MAX_MM:
        return (
            False,
            f'efector a {r:.0f} mm de la base, '
            f'máximo {ALCANCE_MAX_MM:.0f}'
        )

    if r < ALCANCE_MIN_MM:
        return False, f'efector a {r:.0f} mm de la base, demasiado cerca'

    if z < 0.0:
        return False, f'z = {z:.0f} mm: el efector quedaría bajo la base'

    return True, ''

# 11. Paso articular máximo
def paso_articular(q_desde, q_hasta):
    """Mayor variación articular entre dos configuraciones, en radianes."""
    if len(q_desde) != 6 or len(q_hasta) != 6:
        raise ValueError('paso_articular requiere dos vectores de 6 articulaciones')

    return max(
        abs(b - a)
        for a, b in zip(q_desde, q_hasta)
    )
