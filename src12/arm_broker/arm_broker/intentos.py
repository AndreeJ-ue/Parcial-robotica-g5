""" Registro de los intentos de agarre y error por cinemática directa — Pregunta 2 """

""" El enunciado pide 10 intentos, la tasa de éxito, y para cada intento exitoso el error entre
la posición solicitada y la alcanzada, calculado con la FK del RB-2. El broker no devuelve la
pose alcanzada, así que se toma del último /joint_states recibido (suscripción de solo lectura). """

import csv
import math
import os

from arm_broker import fk

CABECERA = ['intento', 'frase', 'objeto', 'color', 'zona', 'exito',
            'q_solicitada', 'q_alcanzada', 'error_mm']


def error_mm(q_solicitada, q_alcanzada):
    """Distancia euclídea en mm entre el efector en la pose pedida y en la alcanzada (FK del RB-2)"""
    x1 = fk.fk(list(q_solicitada))
    x2 = fk.fk(list(q_alcanzada))
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(x1, x2)))


def preparar_csv(ruta):
    """Crea el CSV de intentos con su cabecera si no existe"""
    if not os.path.exists(ruta):
        with open(ruta, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(CABECERA)


def registrar(ruta, intento, frase, objeto, color, zona, exito,
              q_solicitada, q_alcanzada, error):
    """Agrega una fila al CSV de intentos (una por intento de agarre)"""
    with open(ruta, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([
            intento, frase, objeto, color, zona, bool(exito),
            ' '.join(f'{v:.4f}' for v in q_solicitada),
            ' '.join(f'{v:.4f}' for v in q_alcanzada),
            f'{error:.2f}',
        ])


def tasa_exito(ruta):
    """Lee el CSV y calcula la tasa de éxito (exitos / intentos)"""
    total = exitos = 0
    if not os.path.exists(ruta):
        return 0, 0, 0.0
    with open(ruta, newline='', encoding='utf-8') as f:
        for fila in csv.DictReader(f):
            total += 1
            if str(fila.get('exito', '')).strip().lower() in ('true', '1', 'si', 'sí'):
                exitos += 1
    return total, exitos, (exitos / total if total else 0.0)
