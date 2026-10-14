#!/usr/bin/env python3
""" Mide latencia y exactitud del servicio /interpretar_orden — evidencia de la Pregunta 1 """
""" Requiere que interprete_ordenes.py ya esté corriendo en otra terminal """

""" Uso:
    python3 medir_item1.py frases_50.csv resultados_item1.csv

El CSV de entrada necesita al menos una columna "frase". Si además trae las columnas
esperado_accion, esperado_objeto, esperado_color, esperado_permitido (la respuesta correcta
que el equipo definió para cada una de las 50 frases del docente), el script también calcula
la tabla de exactitud de LAYA vs. el clasificador. Sin esas columnas, solo mide latencia.

Por cada frase se hacen DOS llamadas al servicio: una normal (deja que LAYA conteste, y si no
llega a tiempo cae al clasificador) y otra forzando el clasificador puro — así se puede medir
la exactitud de cada método por separado sobre exactamente el mismo conjunto de frases, tal
como pide el enunciado.

Conviene repetir la corrida completa dos veces: una con el laboratorio en calma y otra con los
4 equipos preguntando a la vez, guardando cada corrida en un CSV de salida distinto (ej.
resultados_calma.csv y resultados_carga.csv) para poder compararlas.
"""

import csv
import statistics
import sys

import rclpy
from rclpy.node import Node

from jetcobot_p13_interfaces.srv import InterpretarOrden


# 1. Cliente del servicio
class Medidor(Node):
    def __init__(self):
        super().__init__('medidor_item1', namespace='p13')
        self.cli = self.create_client(InterpretarOrden, 'interpretar_orden')

    def esperar_servicio(self):
        if not self.cli.wait_for_service(timeout_sec=10.0):
            self.get_logger().error('no aparece /interpretar_orden. ¿Está corriendo interprete_ordenes?')
            return False
        return True

    def preguntar(self, frase, forzar_clasificador):
        req = InterpretarOrden.Request()
        req.frase = frase
        req.forzar_clasificador = forzar_clasificador
        fut = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, fut, timeout_sec=15.0)
        if not fut.done():
            fut.cancel()
            raise TimeoutError('El intérprete no respondió en 15 s')
        return fut.result()


# 2. Percentil con interpolación lineal (mismo criterio que usa NumPy por defecto)
def percentil(muestra, p):
    ordenados = sorted(muestra)
    if not ordenados:
        return float('nan')
    k = (len(ordenados) - 1) * (p / 100)
    bajo, alto = int(k), min(int(k) + 1, len(ordenados) - 1)
    if bajo == alto:
        return ordenados[bajo]
    return ordenados[bajo] + (ordenados[alto] - ordenados[bajo]) * (k - bajo)


def main():
    if len(sys.argv) < 2:
        print('uso: python3 medir_item1.py frases.csv [salida.csv]', file=sys.stderr)
        sys.exit(2)

    ruta_entrada = sys.argv[1]
    ruta_salida = sys.argv[2] if len(sys.argv) > 2 else 'resultados_item1.csv'

    with open(ruta_entrada, newline='', encoding='utf-8') as f:
        filas = list(csv.DictReader(f))
    if not filas:
        print(f'{ruta_entrada} está vacío', file=sys.stderr)
        sys.exit(2)

    trae_esperado = all(
        c in filas[0] for c in ('esperado_accion', 'esperado_objeto', 'esperado_color', 'esperado_permitido'))

    rclpy.init()
    nodo = Medidor()
    if not nodo.esperar_servicio():
        rclpy.shutdown()
        sys.exit(1)

    columnas = [
        'frase',
        'laya_accion', 'laya_objeto', 'laya_color', 'laya_prioridad', 'laya_permitido', 'laya_degradada',
        'laya_tiempo_total_s', 'laya_tiempo_red_s', 'laya_tiempo_computo_s',
        'clasif_accion', 'clasif_objeto', 'clasif_color', 'clasif_prioridad', 'clasif_permitido',
    ]
    if trae_esperado:
        columnas += ['acierto_laya', 'acierto_clasificador']

    t_total, t_red, t_computo = [], [], []
    ok_laya_total = ok_clasif_total = 0
    salida_filas = []

    print(f'Midiendo {len(filas)} frases...')

    for fila in filas:
        frase = fila['frase']

        r_laya = nodo.preguntar(frase, forzar_clasificador=False)
        r_clasif = nodo.preguntar(frase, forzar_clasificador=True)

        if not r_laya.degradada:
            t_total.append(r_laya.tiempo_total_s)
            t_red.append(r_laya.tiempo_red_s)
            t_computo.append(r_laya.tiempo_computo_s)

        salida = {
            'frase': frase,
            'laya_accion': r_laya.accion, 'laya_objeto': r_laya.objeto, 'laya_color': r_laya.color,
            'laya_prioridad': r_laya.prioridad, 'laya_permitido': r_laya.permitido,
            'laya_degradada': r_laya.degradada,
            'laya_tiempo_total_s': f'{r_laya.tiempo_total_s:.4f}',
            'laya_tiempo_red_s': f'{r_laya.tiempo_red_s:.4f}',
            'laya_tiempo_computo_s': f'{r_laya.tiempo_computo_s:.4f}',
            'clasif_accion': r_clasif.accion, 'clasif_objeto': r_clasif.objeto, 'clasif_color': r_clasif.color,
            'clasif_prioridad': r_clasif.prioridad, 'clasif_permitido': r_clasif.permitido,
        }

        if trae_esperado:
            ok_laya = (r_laya.accion == fila['esperado_accion'] and r_laya.objeto == fila['esperado_objeto']
                       and r_laya.color == fila['esperado_color']
                       and str(r_laya.permitido) == fila['esperado_permitido'])
            ok_clasif = (r_clasif.accion == fila['esperado_accion'] and r_clasif.objeto == fila['esperado_objeto']
                         and r_clasif.color == fila['esperado_color']
                         and str(r_clasif.permitido) == fila['esperado_permitido'])
            ok_laya_total += int(ok_laya)
            ok_clasif_total += int(ok_clasif)
            salida['acierto_laya'] = ok_laya
            salida['acierto_clasificador'] = ok_clasif

        salida_filas.append(salida)

    with open(ruta_salida, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows(salida_filas)

    def resumen(nombre, datos):
        if not datos:
            print(f'  {nombre}: sin datos (LAYA no respondió a tiempo ninguna vez)')
            return
        print(f'  {nombre}: mediana={statistics.median(datos)*1000:.0f} ms   p95={percentil(datos,95)*1000:.0f} ms')

    print('\n--- RESUMEN LATENCIA ---')
    resumen('tiempo total             ', t_total)
    resumen('tiempo de red (aprox.)   ', t_red)
    resumen('tiempo de cómputo (aprox.)', t_computo)

    if trae_esperado:
        print('\n--- EXACTITUD ---')
        print(f'  LAYA:         {ok_laya_total}/{len(filas)} ({100*ok_laya_total/len(filas):.0f}%)')
        print(f'  Clasificador: {ok_clasif_total}/{len(filas)} ({100*ok_clasif_total/len(filas):.0f}%)')

    print(f'\nGuardado en: {ruta_salida}')

    nodo.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
