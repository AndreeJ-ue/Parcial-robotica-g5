"""Respaldo determinista. No aprende del conjunto de evaluación."""
import re
import unicodedata
from .modelos import Decision


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto.lower())
                   if unicodedata.category(c) != 'Mn')


def clasificar(frase, config, degradada=False, motivo=''):
    texto = normalizar(frase)
    tokens = set(re.findall(r'\b\w+\b', texto))
    base = Decision(degradada=degradada, motivo=motivo)
    if texto.strip(' .!¿?') == 'para' or tokens & {'no', 'nunca', 'cancelar', 'cancela', 'detente', 'golpea',
                 'rompe', 'persona', 'mano', 'humano', 'ignora', 'desactiva'}:
        base.motivo = 'Orden negativa, de parada o no permitida'
        return base
    verbos = {'recoge', 'recoger', 'toma', 'tomar', 'agarra', 'agarrar', 'lleva',
              'llevar', 'traslada', 'trasladar', 'mueve', 'mover', 'coloca', 'colocar',
              'deposita', 'depositar'}
    objetos = {'cubo': {'cubo', 'bloque'}, 'pelota': {'pelota', 'bola'},
               'cilindro': {'cilindro'}, 'botella': {'botella'}, 'objeto': {'objeto', 'pieza'}}
    colores = {'rojo': {'rojo', 'roja'}, 'azul': {'azul'}, 'verde': {'verde'},
               'amarillo': {'amarillo', 'amarilla'}, 'negro': {'negro', 'negra'},
               'blanco': {'blanco', 'blanca'}}
    seleccion_obj = [k for k,v in objetos.items() if tokens & v]
    seleccion_color = [k for k,v in colores.items() if tokens & v]
    if not tokens & verbos or len(seleccion_obj) != 1 or len(seleccion_color) != 1:
        base.motivo = 'Falta acción/objeto/color o hay más de una selección'
        return base
    destinos = re.findall(r'\bzona\s+([a-z0-9]+)\b', texto)
    if len(set(destinos)) > 1:
        base.motivo = 'Destino ambiguo'
        return base
    destino = 'zona_' + destinos[0] if destinos else config.get('destino_por_defecto', 'zona_a')
    if destino not in config['zonas']:
        base.motivo = 'Zona desconocida'
        return base
    prioridad = 10 if tokens & {'urgente', 'urgencia', 'inmediatamente'} else 1
    if tokens & {'tranquilamente', 'despacio'} and prioridad == 1:
        prioridad = 0
    return Decision('recoger_depositar', seleccion_obj[0], seleccion_color[0], prioridad,
                    True, destino, degradada, motivo, 'palabras_clave').validar()
