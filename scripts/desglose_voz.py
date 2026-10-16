"""Pregunta 3: tabla de las órdenes habladas y desglose del tiempo voz → movimiento.

Lee los JSON que deja transcriptor_voz en evidencias/audio/ (o los anotados con anotar_fin_habla.py):

    python3 scripts/desglose_voz.py evidencias/audio/*.json --salida evidencias/p3

Genera <salida>/ordenes.csv (lo transcrito, la decisión, lo que hizo el brazo; columna se_dijo para
completar), <salida>/desglose.csv y <salida>/desglose.png. El total es la SUMA de duraciones medidas
en cada máquina, así que no necesita relojes sincronizados; el tramo de red entre la Raspberry y el
Jetson al enviar el goal queda fuera. Para que percepción, IK y planificación ocurran antes del primer
movimiento, el brazo debe empezar en búsqueda (columna inicio_en_busqueda).
"""
import argparse
import csv
import json
from pathlib import Path

ETAPAS = [('captura', 'Captura tras fin de habla'), ('transcripcion', 'Transcripción (nube)'),
          ('decision', 'Decisión (LAYA)'), ('cola', 'Espera en cola'),
          ('percepcion', 'Percepción'), ('ik', 'Cinemática inversa'), ('planificacion', 'Planificación'),
          ('otros_preparacion', 'Pinza y asentamiento')]


def fila_orden(nombre, d):
    r = d.get('resultado') or {}; dec = d.get('decision') or {}
    if d.get('error'):
        brazo = 'error: ' + d['error']
    elif not d.get('aceptado', True) or (r and not r.get('success') and 'Rechazada' in r.get('message', '')):
        brazo = 'rechazada antes de encolar'
    elif r.get('success'):
        brazo = f"recogió en {r.get('posicion_id')} y depositó en {r.get('destino')}" + (' (simulado)' if r.get('simulado') else '')
    else:
        brazo = 'no completó: ' + r.get('message', '')
    return {'archivo': nombre, 'modo': d.get('modo', ''), 'se_dijo': '', 'transcripcion': d.get('transcripcion', d.get('frase', '')),
            'accion': dec.get('accion', ''), 'objeto': dec.get('objeto', ''), 'color': dec.get('color', ''),
            'prioridad': dec.get('prioridad', ''), 'permitido': dec.get('permitido', ''), 'metodo': dec.get('metodo', ''),
            'que_hizo_el_brazo': brazo, 'correcta': ''}


def fila_desglose(nombre, d):
    r = d.get('resultado') or {}
    if not r.get('success'):
        return None
    prep = r.get('preparacion_s') or 0.0
    medidas = {'percepcion': r.get('percepcion_s') or 0.0, 'ik': r.get('ik_s') or 0.0,
               'planificacion': r.get('planificacion_s') or 0.0}
    fila = {'archivo': nombre, 'captura': d.get('captura_post_habla_s'), 'transcripcion': d.get('transcripcion_s'),
            'decision': d.get('decision_servicio_s'), 'cola': r.get('wait_time_s'), **medidas,
            'otros_preparacion': max(0.0, prep - sum(medidas.values())),
            'inicio_en_busqueda': (r.get('busqueda_s') or 0.0) == 0.0}
    fila['total_s'] = sum(v for k, v in fila.items() if k in dict(ETAPAS) and isinstance(v, (int, float)))
    return fila


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('json', nargs='+'); p.add_argument('--salida', required=True); a = p.parse_args()
    salida = Path(a.salida); salida.mkdir(parents=True, exist_ok=True)
    ordenes, desglose = [], []
    for ruta in a.json:
        d = json.loads(Path(ruta).read_text(encoding='utf-8-sig')); nombre = Path(ruta).name
        ordenes.append(fila_orden(nombre, d))
        f = fila_desglose(nombre, d)
        if f: desglose.append(f)
    with (salida / 'ordenes.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(ordenes[0])); w.writeheader(); w.writerows(ordenes)
    print(f'{len(ordenes)} órdenes → {salida / "ordenes.csv"} (completar se_dijo y correcta)')
    if not desglose:
        print('Ninguna orden completó el movimiento: no hay desglose.'); return
    campos = ['archivo'] + [k for k, _ in ETAPAS] + ['total_s', 'inicio_en_busqueda']
    with (salida / 'desglose.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=campos); w.writeheader(); w.writerows(desglose)
    medias = {k: sum((f[k] or 0.0) for f in desglose) / len(desglose) for k, _ in ETAPAS}
    total = sum(medias.values())
    for k, etiqueta in ETAPAS:
        print(f'  {etiqueta:28s} {medias[k]:7.3f} s  {100 * medias[k] / total if total else 0:5.1f} %')
    dominante = max(medias, key=medias.get)
    print(f'  {"Total medio":28s} {total:7.3f} s · etapa dominante: {dict(ETAPAS)[dominante]}')
    if any(f['captura'] is None for f in desglose):
        print('  Aviso: falta captura tras fin de habla en algunas órdenes (anotar con anotar_fin_habla.py)')
    if not all(f['inicio_en_busqueda'] for f in desglose):
        print('  Aviso: alguna orden empezó fuera de búsqueda; su primer movimiento fue ir a búsqueda')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, eje = plt.subplots(figsize=(8, 4), layout='constrained')
    izquierda = 0.0
    for k, etiqueta in ETAPAS:
        eje.barh(['Media'], [medias[k]], left=izquierda, label=etiqueta); izquierda += medias[k]
    eje.set_xlabel('Segundos desde el fin de habla hasta el primer comando al brazo')
    eje.legend(loc='upper center', bbox_to_anchor=(0.5, -0.25), ncol=4, fontsize=8, frameon=False)
    eje.set_title(f'Desglose voz → movimiento ({len(desglose)} órdenes, total medio {total:.2f} s)')
    fig.savefig(salida / 'desglose.png', dpi=180); plt.close(fig)
    print(f'Figura: {salida / "desglose.png"}')


if __name__ == '__main__':
    main()
