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
from .posiciones import usa_posiciones, validar, comprobar_busqueda


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
        self.medida_lock=threading.Lock();self.medida=None;self.medida_t=0.0
        self.grupo=ReentrantCallbackGroup()
        if usa_posiciones(self.config):
            from sensor_msgs.msg import JointState
            self.sub_medida=self.create_subscription(JointState,'/arm/joint_states_measured',self.recibir_medida,10,callback_group=self.grupo)
        self.camara=CameraFeed(self.config['camara']['indice'],self.config['camara'].get('resolucion_calibracion_px')) if self.config['modo']=='real' else None
        self.servicio=self.create_service(LocalizarObjeto,'/localizar_objeto',self.resolver,callback_group=self.grupo)
    def recibir_medida(self,msg):
        from arm_broker.fk import JOINT_NAMES,dentro_de_limites
        if len(msg.name)!=len(msg.position) or len(set(msg.name))!=len(msg.name):return
        por_nombre=dict(zip(msg.name,msg.position))
        if not all(n in por_nombre for n in JOINT_NAMES):return
        q=[por_nombre[n] for n in JOINT_NAMES]
        if not dentro_de_limites(q)[0]:return
        with self.medida_lock:self.medida=q;self.medida_t=time.monotonic()
    def verificar_busqueda(self):
        with self.medida_lock:
            if self.medida is None or time.monotonic()-self.medida_t>self.config['manipulacion']['busqueda'].get('edad_max_medida_s',2.0):
                raise FalloTarea('Percepción requiere postura articular medida reciente')
            comprobar_busqueda(self.medida,self.config)
    def resolver(self,req,res):
        try:
            d=Decision('recoger_depositar',req.objeto,req.color,1,True)
            if self.camara is None: raise FalloTarea('Percepción real deshabilitada en modo simulado')
            if not usa_posiciones(self.config):raise FalloTarea('Estrategia de manipulación no soportada')
            from .vision import mapa_posiciones,seleccionar_posicion
            validar(self.config,real=True);self.verificar_busqueda()
            frame=self.camara.posterior()
            self.verificar_busqueda()
            mapa=mapa_posiciones(frame,self.config)
            posicion,pose,_=seleccionar_posicion(mapa,d,self.config)
            res.posicion_id=posicion;res.mapa_colores_json=json.dumps(mapa,ensure_ascii=False)
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
