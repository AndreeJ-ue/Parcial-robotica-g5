import json
from pathlib import Path


def cargar(ruta):
    datos = json.loads(Path(ruta).read_text(encoding='utf-8-sig'))
    if datos.get('modo') not in ('simulado', 'real'):
        raise ValueError('modo debe ser simulado o real')
    for clave in ('catalogo', 'zonas', 'interpretacion', 'hardware'):
        if clave not in datos:
            raise ValueError(f'falta {clave}')
    return datos
