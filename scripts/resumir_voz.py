"""Solo calcula latencias entre máquinas con sincronización explícitamente confirmada."""
import argparse
import json
from pathlib import Path


def resumir(fila,relojes):
    r=fila.get('resultado',{});fin=fila.get('fin_habla_wall_ns',0);inicio=r.get('inicio_movimiento_wall_ns',0)
    if not relojes or fila.get('modo')!='voz' or r.get('simulado',True) or not fin or not inicio:
        return {'request_id':fila.get('request_id'),'latencia_total_s':None,'motivo':'Falta voz en vivo, movimiento real o sincronización confirmada'}
    total=(inicio-fin)/1e9
    if total<0:raise ValueError('Timestamps incompatibles; revisar relojes')
    campos={'captura_post_habla':fila.get('captura_post_habla_s'), 'nube':fila.get('transcripcion_s'),
            'decision':fila.get('decision_servicio_s'),'cola':r.get('wait_time_s'),'preparacion':r.get('preparacion_s')}
    medidos=[x for x in campos.values() if x is not None]
    return {'request_id':fila.get('request_id'),'latencia_total_s':total,'componentes_s':campos,
            'residuo_s':total-sum(medidos) if len(medidos)==len(campos) else None,
            'detalle_preparacion_s':{k:r.get(k) for k in ('percepcion_s','ik_s','planificacion_s','gripper_previo_s')}}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archivo');p.add_argument('--relojes-confirmados',action='store_true');a=p.parse_args()
    contenido=Path(a.archivo).read_text(encoding='utf-8-sig')
    filas=[json.loads(contenido)] if Path(a.archivo).suffix=='.json' else [json.loads(x) for x in contenido.splitlines() if x.strip()]
    print(json.dumps([resumir(x,a.relojes_confirmados) for x in filas],ensure_ascii=False,indent=2))
