"""Genera una traza (CSV en radianes) para probar UNA pose enseñada con el broker RB2 y su cliente.

Uso típico, con el brazo ya en la postura de búsqueda:
    python3 scripts/traza_poses.py --config config/prueba_p2.local.json --pose P1 --salida evidencias/traza_P1.csv
    ros2 run arm_broker cliente --ros-args -p client_id:=prueba_P1 -p traza:="$PWD/evidencias/traza_P1.csv"

La traza va de búsqueda a la pose y vuelve a búsqueda, con pasos <= paso_plan_rad. No abre ROS ni serial.
Con --desde-grados se antepone el tramo desde la postura actual hasta búsqueda.
"""
import argparse
import csv
import math
from pathlib import Path
from _bootstrap import ROOT
from parcial_jetcobot.configuracion import cargar
from parcial_jetcobot.posiciones import q_rad_de
from parcial_jetcobot.articular import interpolar


def puntos(config, pose, desde_grados=None):
    m = config['manipulacion']; h = config['hardware']
    q_b = list(m['busqueda']['q_rad'])
    if pose == 'busqueda':
        objetivo = None
    elif pose in m['posiciones']:
        objetivo = q_rad_de(m['posiciones'][pose], pose)
    elif pose in config['zonas']:
        objetivo = q_rad_de(config['zonas'][pose], pose)
    else:
        raise ValueError('Pose desconocida: usar busqueda, P1..P4 o ' + ', '.join(config['zonas']))
    tramos = []
    if desde_grados is not None:
        tramos.append(([math.radians(v) for v in desde_grados], q_b))
    if objetivo is not None:
        tramos += [(q_b, objetivo), (objetivo, q_b)]
    if not tramos:
        raise ValueError('Para busqueda indica --desde-grados con la postura actual')
    salida = []
    for a, b in tramos:
        salida += [q for _, q in interpolar(a, b, h['paso_plan_rad'], h['velocidad_articular_rad_s'])[1:]]
    return salida


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--config', default=str(ROOT / 'src/parcial_jetcobot/config/posiciones_fijas.articular.example.json'))
    p.add_argument('--pose', required=True)
    p.add_argument('--desde-grados', type=float, nargs=6, metavar='J')
    p.add_argument('--salida', required=True)
    a = p.parse_args()
    filas = puntos(cargar(a.config), a.pose, a.desde_grados)
    destino = Path(a.salida); destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', newline='') as f:
        f.write(f'# traza {a.pose}: {len(filas)} puntos en radianes\n')
        csv.writer(f).writerows([[f'{v:.6f}' for v in q] for q in filas])
    print(f'{destino}: {len(filas)} puntos')


if __name__ == '__main__':
    main()
