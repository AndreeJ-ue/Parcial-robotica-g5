"""Evalúa etiquetas congeladas. LAYA real se invoca solamente a través del nodo ROS."""
import argparse
import csv
import hashlib
import json
import time
import uuid
from pathlib import Path
from _bootstrap import ROOT
from parcial_jetcobot.configuracion import cargar
from parcial_jetcobot.clasificador import clasificar


def correcta(fila,d):
    esperado=fila['permitido']=='true'
    if esperado!=d.permitido or fila['accion']!=d.accion:return False
    if not esperado:return True
    return all(str(getattr(d,k))==fila[k] for k in ('objeto','color','prioridad','destino'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--metodo',choices=['palabras','servicio'],required=True)
    p.add_argument('--frases',default=str(ROOT/'datos/frases_50.csv'))
    p.add_argument('--config',default=str(ROOT/'src/parcial_jetcobot/config/simulacion.json'))
    p.add_argument('--salida',required=True);p.add_argument('--condicion',choices=['calma','carga'],default='calma')
    p.add_argument('--repeticiones',type=int,default=1);p.add_argument('--timeout',type=float,default=10)
    a=p.parse_args()
    if a.repeticiones<1 or a.timeout<=0:p.error('repeticiones y timeout deben ser positivos')
    c=cargar(a.config);ruta=Path(a.frases);sha=hashlib.sha256(ruta.read_bytes()).hexdigest()
    with ruta.open(encoding='utf-8-sig',newline='') as archivo:filas=list(csv.DictReader(archivo))
    nodo=None;ros=None
    if a.metodo=='servicio':
        import rclpy as ros
        from rclpy.node import Node
        from arm_broker_interfaces.srv import InterpretarOrden
        from parcial_jetcobot.ros_util import de_msg
        ros.init();nodo=Node('evaluador_'+uuid.uuid4().hex[:8])
        cli=nodo.create_client(InterpretarOrden,'/interpretar_orden')
        if not cli.wait_for_service(timeout_sec=a.timeout):raise RuntimeError('Servicio /interpretar_orden no disponible')
    salida=Path(a.salida);salida.parent.mkdir(parents=True,exist_ok=True)
    campos=['id','request_id','repeticion','condicion','dataset_sha256','frase','categoria','metodo','degradada','correcta',
            'latencia_servicio_ms','latencia_total_ms','http_ms','calculo_servidor_ms','resto_http_ms','decision_json','error']
    try:
        with salida.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=campos);w.writeheader()
            for repeticion in range(a.repeticiones):
                for fila in filas:
                    inicio=time.perf_counter();rid=uuid.uuid4().hex
                    datos=dict(id=fila['id'],request_id=rid,repeticion=repeticion+1,condicion=a.condicion,
                               dataset_sha256=sha,frase=fila['frase'],categoria=fila['categoria'],metodo='error',correcta=False)
                    try:
                        if nodo:
                            req=InterpretarOrden.Request();req.frase=fila['frase'];req.request_id=rid
                            fut=cli.call_async(req);ros.spin_until_future_complete(nodo,fut,timeout_sec=a.timeout)
                            if not fut.done():fut.cancel();raise TimeoutError('Servicio excedió plazo')
                            d=de_msg(fut.result().decision)
                        else:
                            t_clave=time.perf_counter();d=clasificar(fila['frase'],c)
                            d.latencia_total_ms=(time.perf_counter()-t_clave)*1000
                        datos.update(metodo=d.metodo,degradada=d.degradada,correcta=correcta(fila,d),
                                     latencia_total_ms=d.latencia_total_ms,http_ms=d.http_ms,
                                     calculo_servidor_ms=d.calculo_servidor_ms,resto_http_ms=d.resto_http_ms,
                                     decision_json=json.dumps(d.dict(),ensure_ascii=False))
                    except (RuntimeError,ValueError,TimeoutError,AttributeError) as exc:datos['error']=type(exc).__name__
                    datos['latencia_servicio_ms']=(time.perf_counter()-inicio)*1000
                    w.writerow(datos)
        print(f'{len(filas)*a.repeticiones} muestras guardadas en {salida}; SHA256={sha}')
    finally:
        if nodo:nodo.destroy_node();ros.shutdown()

if __name__=='__main__':main()
