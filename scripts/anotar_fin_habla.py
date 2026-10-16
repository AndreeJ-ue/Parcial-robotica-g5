"""Anotación posterior del final de habla en audio capturado en vivo."""
import argparse
import json
import math
from pathlib import Path

def anotar(datos,offset):
    inicio=datos.get('inicio_captura_wall_ns',0);fin=datos.get('fin_captura_wall_ns',0)
    if not inicio or not fin or datos.get('modo')!='voz':raise ValueError('Se requiere captura de voz en vivo con timestamps guardados')
    duracion=(fin-inicio)/1e9
    if not math.isfinite(offset) or not 0<=offset<=duracion:raise ValueError('Offset fuera de la duración capturada')
    d=dict(datos,fin_habla_wall_ns=inicio+int(offset*1e9),fin_habla_confirmado=True,
           captura_post_habla_s=duracion-offset,fin_habla_offset_s=offset,
           anotacion='Fin de habla revisado posteriormente en el audio')
    return d

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('contexto_json');p.add_argument('--offset',type=float,required=True);p.add_argument('--salida',required=True);a=p.parse_args()
    origen=Path(a.contexto_json);salida=Path(a.salida)
    if origen.resolve()==salida.resolve():p.error('Conservar el JSON original; elegir otra salida')
    datos=anotar(json.loads(origen.read_text(encoding='utf-8-sig')),a.offset)
    salida.write_text(json.dumps(datos,ensure_ascii=False,indent=2),encoding='utf-8')
