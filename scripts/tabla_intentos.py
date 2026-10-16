"""Tabla de intentos de la pregunta 2 a partir de evidencias/tareas.jsonl del broker_parcial.

    python3 scripts/tabla_intentos.py --tareas evidencias/tareas.jsonl --ultimos 10 --salida evidencias/intentos.csv

`exito_software` solo indica que la secuencia terminó; completar `exito_fisico` (si/no) mirando
si el objeto correcto quedó en la zona correcta. La tasa oficial se calcula con esa columna.
"""
import argparse
import csv
import json
from pathlib import Path

CAMPOS = ['n', 'request_id', 'client_id', 'frase', 'color', 'prioridad', 'degradada', 'posicion_id', 'destino',
          'exito_software', 'simulado', 'error_fk_mm', 'error_fk_recogida_mm', 'espera_cola_s', 'motivo', 'exito_fisico']


def filas(lineas):
    salida = []
    for linea in lineas:
        if not linea.strip():
            continue
        t = json.loads(linea); d = t.get('decision', {})
        salida.append({'request_id': t.get('request_id', ''), 'client_id': t.get('client_id', ''), 'frase': t.get('frase', ''),
                       'color': d.get('color', ''), 'prioridad': d.get('prioridad', ''), 'degradada': d.get('degradada', ''),
                       'posicion_id': t.get('posicion_id', ''), 'destino': t.get('destino', ''),
                       'exito_software': t.get('exito', False), 'simulado': t.get('simulado', True),
                       'error_fk_mm': round(t['error_fk_mm'], 2) if t.get('error_fk_mm', -1) >= 0 else '',
                       'error_fk_recogida_mm': round(t['error_fk_recogida_mm'], 2) if t.get('error_fk_recogida_mm', -1) >= 0 else '',
                       'espera_cola_s': round(t.get('wait_time_s', 0.0), 3), 'motivo': t.get('motivo', ''), 'exito_fisico': ''})
    return salida


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--tareas', default='evidencias/tareas.jsonl'); p.add_argument('--ultimos', type=int, default=10)
    p.add_argument('--salida', required=True)
    a = p.parse_args()
    datos = filas(Path(a.tareas).read_text(encoding='utf-8').splitlines())[-a.ultimos:]
    for i, f in enumerate(datos, 1):
        f['n'] = i
    destino = Path(a.salida)
    if destino.exists():
        p.error('La salida ya existe; elige otro nombre para no sobrescribir la tabla anotada')
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS); w.writeheader(); w.writerows(datos)
    ok = sum(1 for f in datos if f['exito_software'])
    errores = [f['error_fk_mm'] for f in datos if f['error_fk_mm'] != '']
    print(f'{len(datos)} intentos · secuencias completas: {ok}/{len(datos)}')
    if errores:
        print(f'error FK depósito: medio {sum(errores)/len(errores):.2f} mm · máximo {max(errores):.2f} mm')
    print(f'Completar la columna exito_fisico en {destino}')


if __name__ == '__main__':
    main()
