""" Cliente HTTP contra LAYA (servidor del laboratorio) — Ítem 1 (Pregunta 1) """

""" LAYA no es un nodo de ROS 2: se le habla por HTTP. En este módulo vive todo lo que sabe
armar la consulta tipada y leer la respuesta; interprete_ordenes.py no conoce HTTP. """

import statistics
import time

import requests


def _consulta_tipada(objetos, colores, acciones):
    """Arma las preguntas cerradas que recibe LAYA. Cada una es de tipo choice (elige una opción
    de una lista), score (marca un nivel de una escala) o noul (sí/no). LAYA nunca redacta texto
    libre, así que su salida siempre se puede leer sin ambigüedad."""
    return {
        'accion': {
            'type': 'choice',
            'instructions': '¿Qué acción le pide la frase al brazo robótico?',
            'criteria': list(acciones) + ['desconocido'],
        },
        'objeto': {
            'type': 'choice',
            'instructions': '¿De que forma del objeto se habla?',
            'criteria': list(objetos) + ['desconocido'],
        },
        'color': {
            'type': 'choice',
            'instructions': '¿De qué color es el objeto mencionado en la frase?',
            'criteria': list(colores) + ['ninguno'],
        },
        'prioridad': {
            'type': 'score',
            'instructions': '¿Qué tan urgente suena la frase, del 0 (nada urgente) al 3 (máxima urgencia) en entero?',
            'criteria': ['0', '1', '2', '3'],
        },
        'permitido': {
            'type': 'noul',
            'instructions': '¿Es una orden segura y razonable de ejecutar sobre una mesa de trabajo real respecto a un brazo robotico?',
        },
    }


def _campo(answers, qid, por_defecto):
    """Devuelve el valor de una pregunta dentro de la respuesta de LAYA. Tolera varios nombres
    de campo porque el formato exacto solo se confirma hablando con el servidor real del
    laboratorio (ver herramientas/probar_laya.py). Si no reconoce ninguno, deja el valor por
    defecto."""
    item = answers.get(qid, {})
    if not isinstance(item, dict):
        return item if item is not None else por_defecto
    for nombre in ('choice', 'score', 'noul', 'label', 'value', 'answer'):
        if nombre in item and item[nombre] is not None:
            return item[nombre]
    return por_defecto


def preguntar(url, api_key, frase, timeout_s, objetos, colores, acciones):
    """Le plantea a LAYA una consulta tipada sobre `frase`, respetando timeout_s al pie de la
    letra. Devuelve (dict_decisión, json_crudo). Si algo sale mal (timeout, HTTP de error, JSON
    inválido...), lanza una excepción y quien llama decide qué hacer: en interprete_ordenes.py
    eso activa el clasificador local."""
    cuerpo_peticion = {
        'state': {'body': frase},
        'questions': _consulta_tipada(objetos, colores, acciones),
    }
    cabeceras = {'content-type': 'application/json'}
    if api_key:
        cabeceras['authorization'] = f'Bearer {api_key}'

    respuesta = requests.post(f'{url}/v1/systemone', json=cuerpo_peticion,
                              headers=cabeceras, timeout=timeout_s)
    respuesta.raise_for_status()
    json_resp = respuesta.json()
    answers = json_resp.get('answers', json_resp)  # por si el server no envuelve en "answers"

    accion = str(_campo(answers, 'accion', 'desconocido'))
    objeto = str(_campo(answers, 'objeto', 'desconocido'))
    color = str(_campo(answers, 'color', 'ninguno'))
    prioridad_cruda = _campo(answers, 'prioridad', 1)
    permitido_crudo = _campo(answers, 'permitido', True)

    try:
        prioridad = int(round(float(prioridad_cruda)))
    except (TypeError, ValueError):
        prioridad = 1

    if isinstance(permitido_crudo, str):
        permitido = permitido_crudo.strip().lower() in ('si', 'sí', 'true', 'yes', '1')
    elif isinstance(permitido_crudo, (int, float)):
        permitido = float(permitido_crudo) >= 0.5
    else:
        permitido = bool(permitido_crudo)

    decision = {
        'accion': accion,
        'objeto': objeto,
        'color': color,
        'prioridad': max(0, min(255, prioridad)),
        'permitido': permitido,
        'motivo': '' if permitido else 'LAYA marcó la orden como no permitida',
    }
    return decision, json_resp


def medir_red_base(url, api_key, n=5):
    """Golpea /health n veces (trabajo mínimo del servidor) para estimar cuánto de la latencia
    total hacia /v1/systemone es puramente red. LAYA no reporta su propio tiempo de cómputo en
    la respuesta, así que el reparto se aproxima: tiempo_computo ≈ tiempo_total − esta base.
    Si en el servidor real la respuesta SÍ trae un campo de tiempo propio (revisarlo con
    herramientas/probar_laya.py), úsese directo en vez de esta aproximación."""
    cabeceras = {}
    if api_key:
        cabeceras['authorization'] = f'Bearer {api_key}'
    muestras = []
    for _ in range(n):
        t0 = time.time()
        requests.get(f'{url}/health', headers=cabeceras, timeout=5.0)
        muestras.append(time.time() - t0)
    return statistics.median(muestras)
