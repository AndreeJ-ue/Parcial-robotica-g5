""" Coherencia de una decisión tipada — común a LAYA y al clasificador local """

""" Regla dura del parcial: si la acción no se reconoce, la orden NO se ejecuta, y una frase
con algo prohibido NUNCA queda permitida (aunque el modelo diga que sí). Este módulo concentra
esa comprobación en un solo lugar y NO importa ROS 2, para que la apliquen igual
interprete_ordenes.py y las herramientas (ver herramientas/verificar_decisiones.py) """

from arm_broker import clasificador_palabras_clave as clasificador


# Acciones que el orquestador sabe ejecutar; cualquier otra se rechaza en la admisión
ACCIONES_VALIDAS = ('agarrar', 'soltar', 'mover', 'detener')


def accion_reconocida(decision):
    """True si la decisión trae una acción que está en la lista cerrada de ACCIONES_VALIDAS"""
    return str(decision.get('accion', '')).strip().lower() in ACCIONES_VALIDAS


def aplicar_reglas(decision, frase=''):
    """Corrige una decisión para que `permitido=True` siempre tenga una razón de ser:

    - la frase menciona algo prohibido → permitido=False (aunque LAYA haya dicho que sí);
    - la acción no se reconoce        → permitido=False (no se ejecuta lo que no se entiende);
    - quedó en permitido=False sin motivo → se le pone uno genérico.

    Retorna el mismo dict (modificado) para poder encadenar la llamada.
    """
    if clasificador.tiene_prohibido(frase or decision.get('frase', '')):
        decision['permitido'] = False
        decision['motivo'] = ('la frase menciona algo fuera de lo permitido '
                              '(palabra clave prohibida)')
    elif not accion_reconocida(decision):
        decision['permitido'] = False
        decision['motivo'] = (decision.get('motivo')
                              or 'no se reconoció ninguna acción válida en la frase')
    elif not decision.get('permitido', False):
        decision['motivo'] = (decision.get('motivo')
                              or 'la orden quedó marcada como no permitida')
    return decision
