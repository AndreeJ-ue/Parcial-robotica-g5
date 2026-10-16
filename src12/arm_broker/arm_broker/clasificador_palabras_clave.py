""" Clasificador de respaldo por palabras clave — Pregunta 1 del Parcial """
""" No es IA: es una regla local y determinística. Se usa cuando LAYA no contesta a tiempo,
o cuando se lo fuerza (forzar_clasificador=True) para medir su exactitud por separado """
""" AJUSTEN estas listas a los objetos y colores reales que tengan sobre la mesa """

ACCIONES = {
    'agarrar': ['agarra', 'agarrar', 'recoge', 'recoger', 'toma', 'tomar', 'coge', 'coger'],
    'soltar': ['suelta', 'soltar', 'deja', 'dejar', 'deposita', 'depositar', 'coloca', 'colocar'],
    'mover': ['mueve', 'mover', 'lleva', 'llevar', 'trae', 'traer','muevete','anda'],
    'detener': ['para', 'parar', 'detente', 'detener', 'alto', 'stop', 'cancela', 'cancelar'],
}

OBJETOS = {
    'cubo': ['cubo', 'cubito', 'bloque', 'caja'],
    'cilindro': ['cilindro', 'tubo'],
    'esfera': ['esfera', 'bola', 'pelota'],
}

COLORES = {
    'rojo': ['rojo', 'roja'],
    'verde': ['verde','verd',],
    'azul': ['azul'],
    'amarillo': ['amarillo', 'amarilla'],
}

# Palabras que, si aparecen, hacen que la orden se marque como no permitida.
# Ejemplo: objetos que no están sobre la mesa, o acciones peligrosas/fuera de alcance.
PROHIBIDO = ['destornillador', 'tijera', 'tijeras', 'cuchillo', 'persona', 'mano']


def _buscar(frase, diccionario):
    """Devuelve la primera clave del diccionario cuya lista de palabras aparece en la frase"""
    for clave, palabras in diccionario.items():
        if any(palabra in frase for palabra in palabras):
            return clave
    return None


def tiene_prohibido(frase):
    """True si la frase menciona algo de PROHIBIDO. Es la única regla sobre esa lista, y
    decisiones.py la reutiliza para que LAYA y el clasificador local la apliquen igual"""
    f = frase.lower()
    return any(palabra in f for palabra in PROHIBIDO)


def clasificar(frase):
    """Entrada: frase en español (string). Salida: dict con los mismos campos que arma
    cliente_laya.preguntar(), para que interprete_ordenes.py los trate igual sin importar
    cuál de los dos métodos contestó"""
    f = frase.lower().strip()

    accion = _buscar(f, ACCIONES) or 'desconocido'
    objeto = _buscar(f, OBJETOS) or 'desconocido'
    color = _buscar(f, COLORES) or 'ninguno'

    prohibido = tiene_prohibido(f)
    permitido = not prohibido and accion != 'desconocido'
    if prohibido:
        motivo = 'la frase menciona algo fuera de lo permitido (palabra clave prohibida)'
    elif accion == 'desconocido':
        motivo = 'no se reconoció ninguna acción válida en la frase'
    else:
        motivo = ''

    return {
        'accion': accion,
        'objeto': objeto,
        'color': color,
        'prioridad': 1,      # el clasificador por palabras clave no estima urgencia; prioridad base
        'permitido': permitido,
        'motivo': motivo,
    }
