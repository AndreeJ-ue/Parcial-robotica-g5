import json
import time
import uuid
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from arm_broker_interfaces.action import ManipularObjeto
from arm_broker_interfaces.srv import InterpretarOrden
from .ros_util import configuracion_nodo,de_msg


class ClienteOrdenes(Node):
    def __init__(self,nombre='cliente_ordenes'):
        super().__init__(nombre+'_'+uuid.uuid4().hex[:8])
        self.config=configuracion_nodo(self)
        for k,v in {'client_id':'integrante_1','frase':'','archivo_ordenes':'',
                    'timeout_resultado_s':180.0,'archivo_resultados':'evidencias/clientes.jsonl'}.items():
            self.declare_parameter(k,v)
        self.servicio=self.create_client(InterpretarOrden,'/interpretar_orden')
        self.accion=ActionClient(self,ManipularObjeto,'/manipular_objeto')
    def esperar(self,futuro,timeout):
        rclpy.spin_until_future_complete(self,futuro,timeout_sec=timeout)
        if not futuro.done():
            futuro.cancel();raise TimeoutError('Tiempo límite del cliente excedido')
        if futuro.exception():raise futuro.exception()
        return futuro.result()
    def procesar(self,frase,fin_habla_wall_ns=0,contexto=None):
        request_id=uuid.uuid4().hex
        datos={'request_id':request_id,'client_id':self.get_parameter('client_id').value,
               'frase':frase,'fin_habla_wall_ns':fin_habla_wall_ns,**(contexto or {})}
        try:
            if not self.servicio.wait_for_service(timeout_sec=3):raise RuntimeError('No aparece /interpretar_orden')
            req=InterpretarOrden.Request();req.frase=frase;req.request_id=request_id
            t0=time.perf_counter()
            res=self.esperar(self.servicio.call_async(req),self.config['interpretacion']['timeout_s']+3)
            datos['decision_servicio_s']=time.perf_counter()-t0;datos['decision']=de_msg(res.decision).dict()
            if not self.accion.wait_for_server(timeout_sec=3):raise RuntimeError('No aparece /manipular_objeto')
            goal=ManipularObjeto.Goal();goal.frase=frase;goal.request_id=request_id
            goal.client_id=datos['client_id'];goal.decision=res.decision;goal.fin_habla_wall_ns=fin_habla_wall_ns
            handle=self.esperar(self.accion.send_goal_async(goal,feedback_callback=self.feedback),5)
            datos['aceptado']=handle.accepted
            if handle.accepted:
                try:resultado=self.esperar(handle.get_result_async(),self.get_parameter('timeout_resultado_s').value).result
                except TimeoutError:
                    self.esperar(handle.cancel_goal_async(),3)
                    raise
                campos=['success','simulado','message','wait_time_s','exec_time_s','preparacion_s',
                        'gripper_previo_s','percepcion_s','ik_s','planificacion_s','gripper_s','movimiento_s',
                        'error_fk_mm','inicio_comando_wall_ns','inicio_movimiento_wall_ns','posicion_id','mapa_colores_json',
                        'destino','busqueda_s','retorno_s','planificacion_busqueda_s','planificacion_retorno_s',
                        'estabilizacion_busqueda_s','estabilizacion_retorno_s']
                datos['resultado']={campo:getattr(resultado,campo) for campo in campos}
            else:datos['resultado']={'success':False,'message':'Rechazada antes de encolar; revisar log/CSV del broker'}
        except (RuntimeError,TimeoutError,ValueError) as exc:datos['error']=str(exc)
        archivo=Path(self.get_parameter('archivo_resultados').value);archivo.parent.mkdir(parents=True,exist_ok=True)
        with archivo.open('a',encoding='utf-8') as f:f.write(json.dumps(datos,ensure_ascii=False)+'\n')
        self.get_logger().info(json.dumps(datos,ensure_ascii=False))
        return datos
    def feedback(self,msg):
        self.get_logger().info(f'Etapa: {msg.feedback.state}; cola: {msg.feedback.queue_position}',throttle_duration_sec=0.5)


def main():
    rclpy.init();nodo=None
    try:
        nodo=ClienteOrdenes()
        fichero=nodo.get_parameter('archivo_ordenes').value
        if fichero:
            for frase in Path(fichero).read_text(encoding='utf-8').splitlines():
                if frase.strip():nodo.procesar(frase)
        elif nodo.get_parameter('frase').value:nodo.procesar(nodo.get_parameter('frase').value)
        else:
            while True:
                frase=input('Orden (salir para terminar): ')
                if frase.strip().lower()=='salir':break
                nodo.procesar(frase)
    except (KeyboardInterrupt,EOFError):pass
    finally:
        if nodo:nodo.destroy_node()
        if rclpy.ok():rclpy.shutdown()
