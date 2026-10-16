#!/usr/bin/env python3
"""Métricas de eventos completos, sin estimar esperas a partir del muestreo de cola."""
import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict


def p95(valores):
    return sorted(valores)[max(0, math.ceil(0.95 * len(valores)) - 1)] if valores else None


def resumen(ruta):
    with open(ruta, newline='', encoding='utf-8') as archivo:
        filas = list(csv.DictReader(archivo))
    finales = {}
    for fila in filas:
        if fila['evento'] in ('COMPLETADO', 'CANCELADO', 'ERROR'):
            if fila['goal_id'] in finales:
                raise ValueError('UUID final duplicado: revisar CSV/corridas mezcladas')
            finales[fila['goal_id']] = fila
    aceptados = {f['goal_id'] for f in filas if f['evento'] == 'ACEPTADO'}
    por_cliente = Counter({f['client_id']: 0 for f in filas if f['evento'] == 'ACEPTADO'})
    esperas = defaultdict(list)
    for fila in finales.values():
        if fila['evento'] == 'COMPLETADO':
            por_cliente[fila['client_id']] += 1
            esperas[int(fila['priority'])].append(float(fila['wait_time_s']))
    valores = list(por_cliente.values())
    jain = (sum(valores)**2 / (len(valores) * sum(x*x for x in valores))
            if valores and any(valores) else None)
    return {'finales': Counter(f['evento'] for f in finales.values()),
            'pendientes': len(aceptados - finales.keys()),
            'rechazos': Counter(f['motivo'] for f in filas if f['evento'] == 'RECHAZADO'),
            'clientes': dict(por_cliente), 'esperas': dict(esperas), 'jain': jain}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csvs', nargs='+')
    args = parser.parse_args()
    for ruta in args.csvs:
        datos = resumen(ruta)
        print(f'\n{ruta}\nResultados: {dict(datos["finales"])}; pendientes: {datos["pendientes"]}')
        print('Comandos completados por cliente:', datos['clientes'], 'Jain:', datos['jain'])
        print('Rechazos por motivo:', dict(datos['rechazos']))
        for prioridad, esperas in sorted(datos['esperas'].items()):
            print(f'Prioridad {prioridad}: n={len(esperas)}, media={statistics.mean(esperas):.6f}s, '
                  f'p95={p95(esperas):.6f}s, máxima={max(esperas):.6f}s')
        if datos['esperas']:
            menor = min(datos['esperas'])
            print(f'Espera máxima prioridad observada más baja ({menor}): {max(datos["esperas"][menor]):.6f}s')
    print('\nCOMPLETADO significa envío terminado; no acredita precisión física ni ausencia de otros publicadores.')


if __name__ == '__main__':
    main()
