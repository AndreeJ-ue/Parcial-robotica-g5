""" Cliente HTTP hacia el servidor LAYA del laboratorio — Pregunta 1 del Parcial """
""" LAYA no es un nodo ROS 2: se habla por HTTP. Este módulo es la única pieza que sabe
cómo armar la pregunta tipada y leer la respuesta; interprete_ordenes.py no conoce HTTP """

import statistics
import time

import requests


def _preguntas_tipadas(objetos, colores, acciones):
    """Arma las preguntas tipadas que se le mandan a LAYA: cada una elige una opción de una
    lista cerrada (choice), un nivel de una escala (score) o un sí/no (noul) — LAYA nunca
    redacta texto libre, por eso la salida siempre es parseable sin ambigüedad"""
    return {
        'accion': {
            'type': 'choice',
            'instructions': ('¿Qué acción le pide la frase al brazo robótico? Si la frase pide '
                             'llevar o trasladar el objeto de un lugar a otro (lleva, trae, '
                             'mueve, traslada), la acción es "mover"'),
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
            'instructions': ('¿Es una orden segura y razonable de ejecutar por un brazo robótico '
                             'sobre una mesa de trabajo que solo tiene cubos, cilindros y esferas '
                             'de plástico? Si la frase menciona cualquier otra cosa (tijeras, '
                             'cuchillos, personas, etc.) responde "no"'),
        },
    }


def _extraer(answers, qid, por_defecto):
    """Saca el valor de una pregunta de la respuesta de LAYA; tolera varios nombres de campo
    porque el formato exacto solo se confirma hablando con el servidor real del laboratorio
    (ver herramientas/probar_laya.py). Retorna (valor, encontrado): con encontrado=False se usó
    el valor por defecto porque no se reconoció ningún campo de esa pregunta"""
    item = answers.get(qid, {})
    if not isinstance(item, dict):
        if item is None:
            return por_defecto, False
        return item, True
    for clave in ('choice', 'score', 'noul', 'label', 'value', 'answer'):
        if clave in item and item[clave] is not None:
            return item[clave], True
    return por_defecto, False


def _normalizar(valor, validos, por_defecto):
    """Limpia el texto (espacios + minúsculas) y lo valida contra la lista cerrada de la
    pregunta; lo que no esté en la lista cae al valor por defecto. Así nunca se acepta a
    ciegas lo que devuelva el modelo (p.ej. una acción inventada)"""
    texto = str(valor).strip().lower()
    return texto if texto in validos else por_defecto


def preguntar(url, api_key, frase, timeout_s, objetos, colores, acciones):
    """Le hace una pregunta tipada a LAYA sobre `frase`, respetando timeout_s estrictamente"""
    """Retorna (decision_dict, respuesta_cruda_json)"""
    """Lanza una excepción (timeout, HTTP de error, JSON inválido, etc.) si algo sale mal;
    quien llama decide qué hacer — en interprete_ordenes.py eso dispara el clasificador local"""
    payload = {
        'state': {'body': frase},
        'questions': _preguntas_tipadas(objetos, colores, acciones),
    }
    headers = {'content-type': 'application/json'}
    if api_key:
        headers['authorization'] = f'Bearer {api_key}'

    r = requests.post(f'{url}/v1/systemone', json=payload, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    cuerpo = r.json()
    answers = cuerpo.get('answers', cuerpo)  # por si el server no envuelve la respuesta en "answers"

    accion_cruda, accion_ok = _extraer(answers, 'accion', 'desconocido')
    objeto_crudo, objeto_ok = _extraer(answers, 'objeto', 'desconocido')
    color_crudo, color_ok = _extraer(answers, 'color', 'ninguno')
    prioridad_cruda, prioridad_ok = _extraer(answers, 'prioridad', 1)
    # OJO: permitido es el campo de seguridad; si no se puede leer, se asume False (fail-safe),
    # NUNCA True. Un default True es justamente lo que dejaba pasar órdenes no reconocidas
    permitido_crudo, permitido_ok = _extraer(answers, 'permitido', False)

    # Si no se reconoció NINGÚN campo, la respuesta no es la que se pidió: mejor fallar aquí y
    # que interprete_ordenes.py caiga al clasificador local que aceptar una decisión inventada
    if not any((accion_ok, objeto_ok, color_ok, prioridad_ok, permitido_ok)):
        raise ValueError('LAYA respondió algo que no trae ninguno de los campos pedidos '
                         '(accion/objeto/color/prioridad/permitido)')

    accion = _normalizar(accion_cruda, list(acciones) + ['desconocido'], 'desconocido')
    objeto = _normalizar(objeto_crudo, list(objetos) + ['desconocido'], 'desconocido')
    color = _normalizar(color_crudo, list(colores) + ['ninguno'], 'ninguno')

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

    if permitido:
        motivo = ''
    elif not permitido_ok:
        motivo = 'LAYA no devolvió el campo permitido; por seguridad la orden no se ejecuta'
    else:
        motivo = 'LAYA marcó la orden como no permitida'

    decision = {
        'accion': accion,
        'objeto': objeto,
        'color': color,
        'prioridad': max(0, min(255, prioridad)),
        'permitido': permitido,
        'motivo': motivo,
    }
    return decision, cuerpo


def medir_red_base(url, api_key, n=5):
    """Mide n veces /health (trabajo mínimo del servidor) para estimar cuánto de la latencia
    total hacia /v1/systemone es puramente red. LAYA no reporta su propio tiempo de cómputo
    en la respuesta (no está documentado en el repo oficial), así que esto es la forma de
    aproximar ese reparto: tiempo_computo ≈ tiempo_total - esta línea base.
    Si en el servidor real del laboratorio la respuesta SÍ trae un campo de tiempo propio
    (revisarlo con herramientas/probar_laya.py), úsenlo directo en vez de esta aproximación"""
    headers = {}
    if api_key:
        headers['authorization'] = f'Bearer {api_key}'
    tiempos = []
    for _ in range(n):
        t0 = time.time()
        requests.get(f'{url}/health', headers=headers, timeout=5.0)
        tiempos.append(time.time() - t0)
    return statistics.median(tiempos)
