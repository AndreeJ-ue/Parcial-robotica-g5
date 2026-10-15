""" Registro de intentos de agarre y error de cinemática directa — Ítem 2 """

""" El enunciado pide, por cada intento exitoso, el error entre la posición solicitada y la
alcanzada calculado con la cinemática directa del RB-2. Aquí se guarda ese error en milímetros
(‖FK(q_solicitada) − FK(q_alcanzada)‖) junto al resto del intento. """

import csv
import math
import os
import time

from arm_broker import fk

CABECERA = [
    'intento', 't_unix', 'frase', 'objeto', 'color', 'posicion', 'destino',
    'exito', 'q_solicitada_deg', 'q_alcanzada_deg', 'error_mm', 'motivo',
]


def error_fk_mm(q_solicitada_rad, q_alcanzada_rad):
    """Distancia en mm entre las posiciones del efector de dos configuraciones (o None)."""
    if q_solicitada_rad is None or q_alcanzada_rad is None:
        return None
    x1, y1, z1 = fk.fk(list(q_solicitada_rad))
    x2, y2, z2 = fk.fk(list(q_alcanzada_rad))
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)


class RegistroIntentos:

    def __init__(self, ruta):
        self.ruta = ruta
        if not os.path.exists(self.ruta):
            with open(self.ruta, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(CABECERA)

    def registrar(self, intento, frase, objeto, color, posicion, destino, exito,
                  q_solicitada_rad=None, q_alcanzada_rad=None, motivo=''):
        error = error_fk_mm(q_solicitada_rad, q_alcanzada_rad)
        with open(self.ruta, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                intento, f'{time.time():.3f}', frase, objeto, color, posicion, destino,
                bool(exito),
                _grados(q_solicitada_rad), _grados(q_alcanzada_rad),
                '' if error is None else f'{error:.3f}', motivo,
            ])


def _grados(q_rad):
    if q_rad is None:
        return ''
    return ' '.join(f'{math.degrees(v):.3f}' for v in q_rad)
