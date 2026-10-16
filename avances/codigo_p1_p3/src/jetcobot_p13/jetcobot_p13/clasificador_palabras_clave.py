# Configuración de rutas y namespace para las preguntas 1 y 3.
""" Clasificador local de respaldo por palabras clave — Ítem 1 (Pregunta 1) """

""" No es IA: es una regla determinística que vive en la máquina. Entra cuando LAYA se pasa del
tiempo o cuando el cliente lo pide a propósito (forzar_clasificador=True), y así se puede medir
su acierto por separado. AJUSTAR las listas de abajo a los objetos y colores que de verdad haya
sobre la mesa. """

# Verbos que reconoce cada acción.
VERBOS = {
    'agarrar': ['agarra', 'agarrar', 'recoge', 'recoger', 'toma', 'tomar', 'coge', 'coger'],
    'soltar': ['suelta', 'soltar', 'deja', 'dejar', 'deposita', 'depositar', 'coloca', 'colocar'],
    'mover': ['mueve', 'mover', 'lleva', 'llevar', 'trae', 'traer', 'muevete', 'anda'],
    'detener': ['para', 'parar', 'detente', 'detener', 'alto', 'stop', 'cancela', ],
}

# Sinónimos por forma de objeto.
FORMAS = {
    'cubo': ['cubo', 'cubito', 'bloque', 'caja'],
    'cilindro': ['cilindro', 'tubo'],
    'esfera': ['esfera', 'bola', 'pelota'],
}

# Sinónimos por color.
TONOS = {
    'rojo': ['rojo', 'roja'],
    'verde': ['verde', 'verd'],
    'azul': ['azul'],
    'amarillo': ['amarillo', 'amarilla'],
}

# Si alguna de estas palabras aparece, la orden queda marcada como no permitida: objetos que no
# están sobre la mesa o acciones peligrosas / fuera de alcance.
VETADAS = ['destornillador', 'tijera', 'tijeras', 'cuchillo', 'persona', 'mano']


def _primera_clave(frase, tabla):
    """Primera clave de la tabla cuya lista de sinónimos aparezca dentro de la frase (o None)."""
    for clave, sinonimos in tabla.items():
        if any(s in frase for s in sinonimos):
            return clave
    return None


def clasificar(frase):
    """Entrada: frase en español (str). Salida: dict con los MISMOS campos que arma
    cliente_laya.preguntar(), para que interprete_ordenes lo trate igual sin importar cuál de
    los dos métodos respondió."""
    texto = frase.lower().strip()

    accion = _primera_clave(texto, VERBOS) or 'desconocido'
    objeto = _primera_clave(texto, FORMAS) or 'desconocido'
    color = _primera_clave(texto, TONOS) or 'ninguno'

    tiene_vetada = any(palabra in texto for palabra in VETADAS)
    permitido = not tiene_vetada and accion != 'desconocido'
    if tiene_vetada:
        motivo = 'la frase nombra algo fuera de lo permitido (palabra clave vetada)'
    elif accion == 'desconocido':
        motivo = 'no se reconoció ninguna acción válida en la frase'
    else:
        motivo = ''

    return {
        'accion': accion,
        'objeto': objeto,
        'color': color,
        'prioridad': 1,      # el clasificador no estima urgencia; se deja la prioridad base
        'permitido': permitido,
        'motivo': motivo,
    }
