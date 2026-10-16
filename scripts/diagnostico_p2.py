"""Inventario de lectura: consulta ROS sin enviar goals ni comandos articulares."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess


def consultar(argumentos, limite):
    try:
        p = subprocess.run(argumentos, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=limite)
        return {'comando': argumentos, 'codigo': p.returncode,
                'salida': p.stdout, 'error': p.stderr}
    except subprocess.TimeoutExpired:
        return {'comando': argumentos, 'codigo': None, 'error': 'Consulta excedió el plazo'}
    except OSError as exc:
        return {'comando': argumentos, 'codigo': None, 'error': str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nodo-moveit', default='/move_group')
    parser.add_argument('--timeout', type=float, default=8)
    parser.add_argument('--salida', help='Carpeta nueva; no sobrescribe una corrida anterior')
    args = parser.parse_args()
    if not 0 < args.timeout <= 30:
        parser.error('--timeout debe estar entre 0 y 30 segundos')
    marca = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destino = Path(args.salida or f'evidencias/diagnostico_p2_{marca}')
    destino.mkdir(parents=True, exist_ok=False)
    datos = {'fecha_utc': marca, 'maquina': socket.gethostname(),
             'red': {k: os.environ.get(k, '') for k in (
                 'ROS_DOMAIN_ID', 'ROS_DISCOVERY_SERVER', 'ROS_LOCALHOST_ONLY',
                 'RMW_IMPLEMENTATION', 'FASTRTPS_DEFAULT_PROFILES_FILE')},
             'consultas': {}, 'robot_asignado_confirmado': False}
    ros = shutil.which('ros2')
    comandos = [
        ('nodos', ['node', 'list']),
        ('servicios', ['service', 'list', '-t']),
        ('acciones', ['action', 'list', '-t']),
        ('topicos', ['topic', 'list', '-t']),
        ('publicadores_comandos', ['topic', 'info', '/joint_states', '--verbose']),
        ('mediciones_articulares', ['topic', 'info', '/arm/joint_states_measured', '--verbose']),
        ('interfaz_interprete', ['interface', 'show', 'arm_broker_interfaces/srv/InterpretarOrden']),
        ('interfaz_manipulacion', ['interface', 'show', 'arm_broker_interfaces/action/ManipularObjeto']),
        ('modelo_moveit', ['param', 'get', args.nodo_moveit, 'robot_description']),
        ('grupos_moveit', ['param', 'get', args.nodo_moveit, 'robot_description_semantic']),
    ]
    if ros:
        for nombre, comando in comandos:
            print(f'Consultando {nombre}...', flush=True)
            r = consultar([ros, *comando], args.timeout)
            datos['consultas'][nombre] = r
            (destino / f'{nombre}.txt').write_text(r.get('salida', '')+'\n'+r.get('error', ''), encoding='utf-8')
    else:
        datos['error'] = 'ros2 no disponible; cargar el entorno ROS y el workspace en la Raspberry'
    (destino / 'resumen.json').write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Inventario guardado en {destino.resolve()}. No se enviaron comandos al brazo.')
    print('La presencia de servicios no confirma que el Jetson o robot pertenezcan al equipo.')
    return 0 if ros else 1


if __name__ == '__main__':
    raise SystemExit(main())
