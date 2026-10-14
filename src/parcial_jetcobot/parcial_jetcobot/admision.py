"""Comprueba contradicciones explícitas sin sustituir la interpretación LAYA."""
import re
from .clasificador import normalizar

# Una orden de manipulación solicita un objeto y un color. Los colores fuera
# del catálogo se incluyen para impedir que el modelo los traduzca a otro color.
COLORES = {
    'rojo': {'rojo', 'roja'}, 'azul': {'azul'}, 'verde': {'verde'},
    'amarillo': {'amarillo', 'amarilla'}, 'negro': {'negro', 'negra'},
    'blanco': {'blanco', 'blanca'}, 'naranja': {'naranja'},
    'morado': {'morado', 'morada', 'violeta'}, 'rosa': {'rosa', 'rosado', 'rosada'},
    'gris': {'gris'}, 'marron': {'marron', 'cafe'},
}


def validar_color_explicito(frase, decision):
    tokens = set(re.findall(r'\b\w+\b', normalizar(frase)))
    colores = [color for color, palabras in COLORES.items() if tokens & palabras]
    if len(colores) > 1:
        raise ValueError('Orden con varios colores; requiere aclaración antes de encolar')
    if colores and decision.color != colores[0]:
        raise ValueError('Color decidido distinto del color explícito de la frase')
    return decision
