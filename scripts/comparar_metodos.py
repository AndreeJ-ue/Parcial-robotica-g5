"""Pregunta 1: une los CSV de evaluar_frases.py (LAYA y palabras clave) en una sola tabla por frase.

    python3 scripts/comparar_metodos.py --laya evidencias/p1_laya_calma.csv \
        --palabras evidencias/p1_palabras.csv --salida evidencias/p1_comparacion.csv

Imprime la exactitud de cada método y las frases que falla cada uno, agrupadas por categoría,
como insumo para el comentario de media página. Si el CSV de LAYA tiene repeticiones, usa la primera.
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def leer(ruta):
    por_id = {}
    with open(ruta, encoding='utf-8-sig', newline='') as f:
        for fila in csv.DictReader(f):
            por_id.setdefault(fila['id'], fila)
    return por_id


def resumen_decision(fila):
    try:
        d = json.loads(fila.get('decision_json') or '{}')
    except ValueError:
        d = {}
    if not d:
        return fila.get('error') or 'sin decisión'
    if not d.get('permitido'):
        return 'rechazar'
    return f"{d.get('objeto')}/{d.get('color')}/p{d.get('prioridad')}/{d.get('destino')}"


def comparar(laya, palabras):
    filas = []
    for i in sorted(set(laya) | set(palabras)):
        a, b = laya.get(i, {}), palabras.get(i, {})
        base = a or b
        filas.append({'id': i, 'categoria': base.get('categoria', ''), 'frase': base.get('frase', ''),
                      'laya_decision': resumen_decision(a) if a else '', 'laya_metodo': a.get('metodo', ''),
                      'laya_degradada': a.get('degradada', ''), 'laya_correcta': a.get('correcta', ''),
                      'palabras_decision': resumen_decision(b) if b else '', 'palabras_correcta': b.get('correcta', '')})
    return filas


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--laya', required=True); p.add_argument('--palabras', required=True); p.add_argument('--salida', required=True)
    a = p.parse_args()
    filas = comparar(leer(a.laya), leer(a.palabras))
    destino = Path(a.salida); destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0])); w.writeheader(); w.writerows(filas)
    n = len(filas)
    for metodo in ('laya', 'palabras'):
        ok = sum(1 for x in filas if x[metodo + '_correcta'] == 'True')
        print(f'{metodo}: {ok}/{n} correctas ({100 * ok / n:.0f} %)')
        fallos = defaultdict(list)
        for x in filas:
            if x[metodo + '_correcta'] != 'True':
                fallos[x['categoria']].append(x['frase'])
        for categoria, frases in sorted(fallos.items()):
            print(f'  falla en {categoria}: ' + ' | '.join(frases))
    degradadas = sum(1 for x in filas if x['laya_degradada'] == 'True')
    if degradadas:
        print(f'Atención: {degradadas} respuestas de LAYA fueron degradadas (resueltas por el respaldo)')
    print(f'Tabla por frase: {destino}')


if __name__ == '__main__':
    main()
