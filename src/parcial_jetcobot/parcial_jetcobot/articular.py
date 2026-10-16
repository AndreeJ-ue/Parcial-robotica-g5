"""Planificación en espacio articular para las poses enseñadas (modo sin MoveIt).

La "cinemática inversa" de este modo es la solución articular ya enseñada en el brazo
para cada posición P1–P4 y cada depósito; aquí solo se interpola entre poses y se
verifica cada punto con la FK y los límites del RB2. No abre ROS ni puerto serial.
"""
import math
from arm_broker import fk
from .modelos import FalloTarea


def interpolar(inicio, final, paso_max_rad, velocidad_rad_s):
    """Trayectoria [(t_s, q_rad), ...] en línea recta articular.

    El primer punto es la postura de inicio en t=0 (igual que una trayectoria de MoveIt),
    ningún salto entre puntos supera paso_max_rad y el tiempo sale de la velocidad pedida.
    """
    if len(inicio) != 6 or len(final) != 6:
        raise FalloTarea('Se requieren seis articulaciones para planificar')
    if not (math.isfinite(paso_max_rad) and paso_max_rad > 0 and math.isfinite(velocidad_rad_s) and velocidad_rad_s > 0):
        raise FalloTarea('Paso y velocidad articular deben ser positivos')
    distancia = fk.paso_articular(inicio, final)
    n = max(1, math.ceil(distancia / paso_max_rad))
    dt = (distancia / n) / velocidad_rad_s if distancia > 0 else 0.1
    plan = []
    for i in range(n + 1):
        f = i / n
        q = list(final) if i == n else [a + f * (b - a) for a, b in zip(inicio, final)]
        if i > 0:
            ok, motivo = fk.dentro_de_limites(q)
            if ok:
                ok, motivo = fk.dentro_del_workspace(q)
            if not ok:
                raise FalloTarea('Trayectoria articular inválida: ' + motivo)
        plan.append((i * dt, q))
    return plan


def error_fk_mm(q_medida, q_solicitada):
    """Distancia (mm) entre la posición FK alcanzada y la solicitada, con la FK del RB2."""
    return math.dist(fk.fk(q_medida), fk.fk(q_solicitada))
