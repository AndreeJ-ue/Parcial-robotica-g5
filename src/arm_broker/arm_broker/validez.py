""" Coherencia de una orden ya tipada — común a LAYA y al clasificador local (Ítem 1) """

""" Regla dura del parcial: lo que no se entiende NO se ejecuta, y una frase con algo vetado
JAMÁS queda permitida (aunque el proveedor diga que sí). Este módulo reúne esa comprobación en un
solo sitio y deliberadamente NO importa ROS 2: así lo pueden usar por igual el intérprete de
órdenes y las herramientas de análisis (ver analisis/verificar_publicadores.py). """

from arm_broker import clasificador_palabras_clave as clasificador


# Acciones que la cadena de agarre sabe ejecutar de verdad. Cualquier otra se descarta aquí mismo.
ACCIONES_VALIDAS = ('agarrar', 'soltar', 'mover', 'detener')


def accion_valida(decision):
    """True si la decisión trae una acción de la lista cerrada ACCIONES_VALIDAS."""
    return str(decision.get('accion', '')).strip().lower() in ACCIONES_VALIDAS


def corregir(decision, frase=''):
    """Ajusta una decisión para que 'permitido=True' siempre tenga sustento:

    - la frase nombra algo vetado   -> permitido=False (aunque LAYA haya dicho que sí);
    - la acción no se reconoce      -> permitido=False (no se ejecuta lo que no se entiende);
    - quedó en permitido=False sin motivo -> se le pone uno genérico.

    Devuelve el mismo dict (ya modificado) para poder encadenar la llamada.
    """
    if clasificador.tiene_vetada(frase or decision.get('frase', '')):
        decision['permitido'] = False
        decision['motivo'] = ('la frase nombra algo fuera de lo permitido '
                              '(palabra clave vetada)')
    elif not accion_valida(decision):
        decision['permitido'] = False
        decision['motivo'] = (decision.get('motivo')
                              or 'no se reconoció ninguna acción válida en la frase')
    elif not decision.get('permitido', False):
        decision['motivo'] = (decision.get('motivo')
                              or 'la orden quedó marcada como no permitida')
    return decision
