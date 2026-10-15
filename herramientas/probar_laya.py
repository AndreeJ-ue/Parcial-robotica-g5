#!/usr/bin/env python3
""" Prueba rápida y SIN ROS 2 contra el servidor LAYA — correr esto PRIMERO, el día del examen,
apenas tengan la IP y el puerto reales, antes de confiar en interprete_ordenes.py.

Para qué sirve: LAYA no documenta públicamente la forma exacta del JSON que devuelve.
Este script hace una pregunta de prueba y muestra la respuesta cruda completa, para que
puedan confirmar (o ajustar) cómo cliente_laya._campo() lee los campos accion/objeto/
color/prioridad/permitido.

Uso:
    export LAYA_API_KEY=...   # solo si el servidor del laboratorio pide clave
    python3 probar_laya.py http://IP:PUERTO "agarra el cubo rojo"
"""

import json
import os
import sys
import time

import requests


def main():
    if len(sys.argv) < 3:
        print('uso: python3 probar_laya.py http://IP:PUERTO "frase a probar"', file=sys.stderr)
        sys.exit(2)

    base = sys.argv[1].rstrip('/')
    frase = sys.argv[2]
    clave = os.environ.get('LAYA_API_KEY', '')
    cabeceras = {'content-type': 'application/json'}
    if clave:
        cabeceras['authorization'] = f'Bearer {clave}'

    print(f'\n{"=" * 60}\n1) GET {base}/health\n{"=" * 60}')
    inicio = time.time()
    try:
        resp = requests.get(f'{base}/health', headers=cabeceras, timeout=5.0)
        print(f'status={resp.status_code}  ({(time.time() - inicio) * 1000:.0f} ms)')
        print(resp.text[:500])
    except Exception as e:
        print(f'ERROR: no se pudo conectar a {base}/health — {e!r}')
        print('Revisen IP/puerto, que estén en la misma red, y que el server esté arriba.')
        sys.exit(1)

    cuerpo = {
        'state': {'body': frase},
        'questions': {
            'accion': {'type': 'choice', 'instructions': '¿Qué acción pide la frase?',
                       'criteria': ['agarrar', 'soltar', 'mover', 'detener', 'desconocido']},
            'objeto': {'type': 'choice', 'instructions': '¿Sobre qué objeto actúa?',
                       'criteria': ['cubo', 'cilindro', 'esfera', 'desconocido']},
            'color': {'type': 'choice', 'instructions': '¿De qué color es el objeto?',
                      'criteria': ['rojo', 'verde', 'azul', 'amarillo', 'ninguno']},
            'prioridad': {'type': 'score', 'instructions': '¿Qué tan urgente suena, 0 a 3?',
                          'criteria': ['0', '1', '2', '3']},
            'permitido': {'type': 'noul', 'instructions': '¿Es una orden segura de ejecutar?'},
        },
    }

    print(f'\n{"=" * 60}\n2) POST {base}/v1/systemone\n   frase: "{frase}"\n{"=" * 60}')
    inicio = time.time()
    resp = requests.post(f'{base}/v1/systemone', json=cuerpo, headers=cabeceras, timeout=10.0)
    dt = time.time() - inicio
    print(f'status={resp.status_code}  ({dt * 1000:.0f} ms)\n')
    print('--- respuesta cruda completa (revisar aquí los nombres de campo reales) ---')
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    print(f'\n{"=" * 60}\nSi los campos no coinciden con choice/score/noul/label/value/answer,')
    print('ajusten la función _campo() en arm_broker/cliente_laya.py')
    print(f'{"=" * 60}\n')


if __name__ == '__main__':
    main()
