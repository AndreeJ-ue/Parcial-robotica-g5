"""Marca como confirmadas, en una config LOCAL, las partes ya probadas con el brazo supervisado.

    python3 scripts/confirmar_config.py --config config/prueba_p2.local.json busqueda camara pinza P1 zona_rojo
    python3 scripts/confirmar_config.py --config config/prueba_p2.local.json --quitar P1

Claves: busqueda, camara (ROI en búsqueda), pinza (driver/adaptador serial), P1..P4 y zonas.
Solo edita archivos *.local.json; las plantillas compartidas no se tocan.
"""
import argparse
import json
from pathlib import Path


def aplicar(c, claves, valor=True):
    m = c['manipulacion']
    for clave in claves:
        if clave == 'busqueda':
            m['busqueda']['confirmada'] = valor
        elif clave == 'camara':
            c['camara']['calibracion_confirmada'] = valor
        elif clave == 'pinza':
            c['hardware']['adaptador_serial_confirmado'] = valor
        elif clave in m['posiciones']:
            m['posiciones'][clave]['confirmada'] = valor
        elif clave in c['zonas']:
            c['zonas'][clave]['confirmada'] = valor
        else:
            raise ValueError('Clave desconocida: ' + clave)
    return c


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--config', required=True); p.add_argument('--quitar', action='store_true')
    p.add_argument('claves', nargs='+')
    a = p.parse_args(); ruta = Path(a.config)
    if not ruta.name.endswith('.local.json'):
        p.error('Solo se editan configuraciones *.local.json')
    c = aplicar(json.loads(ruta.read_text(encoding='utf-8-sig')), a.claves, not a.quitar)
    ruta.write_text(json.dumps(c, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(('Desmarcado: ' if a.quitar else 'Confirmado: ') + ', '.join(a.claves))


if __name__ == '__main__':
    main()
