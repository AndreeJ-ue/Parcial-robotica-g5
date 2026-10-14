import csv
import json
import threading
import time
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from arm_broker_interfaces.srv import InterpretarOrden,LocalizarObjeto
from .ros_util import configuracion_nodo,a_msg
from .interpretacion import interpretar
from .modelos import Decision,FalloTarea


class Interprete(Node):
    def __init__(self):
        super().__init__('interprete_ordenes')
        self.config=configuracion_nodo(self)
        self.declare_parameter('timeout_s',self.config['interpretacion']['timeout_s'])
        self.config['interpretacion']['timeout_s']=float(self.get_parameter('timeout_s').value)
        self.declare_parameter('archivo_csv','evidencias/interpretacion.csv')
        self.csv=Path(self.get_parameter('archivo_csv').value)
        self.csv.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.Lock()
        self.servicio=self.create_service(InterpretarOrden,'/interpretar_orden',self.resolver,
                                         callback_group=ReentrantCallbackGroup())
    def resolver(self,req,res):
        try: d=interpretar(req.frase,self.config)
        except Exception as exc: d=Decision(motivo=f'Error controlado: {type(exc).__name__}',degradada=True)
        a_msg(d,res.decision)
        fila=dict(request_id=req.request_id,frase=req.frase,wall_time_ns=time.time_ns(),**d.dict())
        with self.lock:
            nuevo=not self.csv.exists() or self.csv.stat().st_size==0
            with self.csv.open('a',newline='',encoding='utf-8') as archivo:
                w=csv.DictWriter(archivo,fieldnames=list(fila))
                if nuevo:w.writeheader()
                w.writerow(fila)
        return res


class Percepcion(Node):
    def __init__(self):
        super().__init__('percepcion_objetos')
        self.config=configuracion_nodo(self)
        from .vision import CameraFeed
        self.camara=CameraFeed(self.config['camara']['indice']) if self.config['modo']=='real' else None
        self.servicio=self.create_service(LocalizarObjeto,'/localizar_objeto',self.resolver)
    def resolver(self,req,res):
        try:
            d=Decision('recoger_depositar',req.objeto,req.color,1,True)
            if self.camara is None: raise FalloTarea('Percepción real deshabilitada en modo simulado')
            from .vision import localizar
            pose=localizar(self.camara.actual(),d,self.config)
            res.pose.header.frame_id=pose.frame_id; res.pose.header.stamp=self.get_clock().now().to_msg()
            res.pose.pose.position.x,res.pose.pose.position.y,res.pose.pose.position.z=pose.xyz_m
            q=res.pose.pose.orientation; q.x,q.y,q.z,q.w=pose.quaternion_xyzw
            res.encontrado=True
        except (FalloTarea,ValueError,RuntimeError) as exc:res.motivo=str(exc)
        return res
    def destroy_node(self):
        if self.camara:self.camara.cerrar()
        return super().destroy_node()


def correr(clase):
    rclpy.init(); nodo=None; ex=MultiThreadedExecutor(num_threads=4)
    try:
        nodo=clase(); ex.add_node(nodo); ex.spin()
    except KeyboardInterrupt:pass
    finally:
        ex.shutdown()
        if nodo:nodo.destroy_node()
        if rclpy.ok():rclpy.shutdown()


def main_interprete():correr(Interprete)
def main_percepcion():correr(Percepcion)
