"""Extiende ArmBroker; comparte su worker, cola, política, reservas y QueueState."""
import json
import time
from pathlib import Path
from dataclasses import asdict
import rclpy
from rclpy.action import ActionServer,GoalResponse
from rclpy.executors import MultiThreadedExecutor
from arm_broker.broker import ArmBroker
from arm_broker.politicas import Pedido
from arm_broker_interfaces.action import ManipularObjeto
from arm_broker_interfaces.srv import LocalizarObjeto,AccionarPinza
from .ros_util import configuracion_nodo,de_msg
from .pipeline import ejecutar,BackendSimulado
from .clasificador import clasificar
from .admision import validar_color_explicito
from .modelos import FalloTarea


class BrokerParcial(ArmBroker):
    def __init__(self):
        # Inicializar lo usado por recibir_medida antes de crear la suscripción heredada.
        self.referencia_movimiento=None;self.inicio_movimiento_wall_ns=0
        super().__init__()
        self.config=configuracion_nodo(self)
        self.declare_parameter('archivo_tareas','evidencias/tareas.jsonl')
        self.archivo_tareas=Path(self.get_parameter('archivo_tareas').value)
        self.archivo_tareas.parent.mkdir(parents=True,exist_ok=True)
        if self.config['modo']=='simulado':
            self.estado.ordenar([0.0]*6)  # semilla explícitamente sintética, jamás hardware
        else:
            from moveit_msgs.srv import GetPositionIK,GetMotionPlan
            h=self.config['hardware']
            self.cli_percepcion=self.create_client(LocalizarObjeto,'/localizar_objeto',callback_group=self.grupo_entrada)
            self.cli_pinza=self.create_client(AccionarPinza,'/arm/accionar_pinza',callback_group=self.grupo_entrada)
            self.cli_ik=self.create_client(GetPositionIK,h['servicio_ik'],callback_group=self.grupo_entrada)
            self.cli_plan=self.create_client(GetMotionPlan,h['servicio_plan'],callback_group=self.grupo_entrada)
        self.manipulacion=ActionServer(self,ManipularObjeto,'/manipular_objeto',
                                      goal_callback=self.admitir_tarea,
                                      handle_accepted_callback=self.encolar_tarea,
                                      cancel_callback=self.cancel_callback,
                                      execute_callback=self.ejecutar_tarea,
                                      callback_group=self.grupo_entrada)

    def goal_callback(self,req):
        return self.rechazar(req,'En broker_parcial usar /manipular_objeto; MoveArm directo deshabilitado')

    def admitir_tarea(self,req):
        try:
            d=de_msg(req.decision)
            if not req.client_id or not req.request_id or not req.frase.strip():raise ValueError('faltan client_id/request_id/frase')
            if not d.permitido:raise ValueError(d.motivo or 'Orden no permitida')
            if d.prioridad not in (0,1,10):raise ValueError('Prioridad fuera del contrato del intérprete')
            if d.destino not in self.config['zonas']:raise ValueError('Destino desconocido')
            # Defensa determinista para órdenes explícitamente prohibidas, sin reemplazar al modelo.
            comprobacion=clasificar(req.frase,self.config)
            if comprobacion.motivo=='Orden negativa, de parada o no permitida':
                raise ValueError(comprobacion.motivo)
            validar_color_explicito(req.frase,d)
            if self.config['modo']=='real':
                from .backend_ros import BackendReal
                BackendReal(self,self.config).estado()
            with self.lock:
                if self._parar.is_set():raise ValueError('broker deteniéndose')
                ref,_=self.estado.referencia()
                if ref is None:raise ValueError('Postura inicial desconocida')
                ok,motivo=self.estado.reservar(ref)
                if not ok:raise ValueError(motivo)
                self.n_aceptados+=1
                self.admisiones[id(req)]=(req,time.monotonic(),self.n_aceptados)
            return GoalResponse.ACCEPT
        except (ValueError,FalloTarea) as exc:
            return self.rechazar(req,str(exc))

    def encolar_tarea(self,handle):
        req=handle.request
        p=Pedido(handle,req.client_id,req.decision.prioridad,[])
        p.feedback_factory=ManipularObjeto.Feedback
        with self.lock:
            _,p.t_llegada,p.secuencia=self.admisiones.pop(id(req))
            self.pendientes.append(p);self.pendientes.sort(key=lambda x:x.secuencia)
            self.por_goal_id[p.goal_id]=p
            self.evento('ACEPTADO',p,motivo=req.request_id)

    def recibir_medida(self,msg):
        with self.lock:anterior=self.estado.t_medida
        super().recibir_medida(msg)
        if self.referencia_movimiento is None or self.inicio_movimiento_wall_ns:
            return
        with self.lock:
            if self.estado.t_medida<=anterior:return
            q=self.estado.q_medida
            if q is not None and max(abs(a-b) for a,b in zip(q,self.referencia_movimiento))>0.01:
                # Recepción en el Jetson, misma base temporal que fin_habla solo con relojes sincronizados.
                self.inicio_movimiento_wall_ns=time.time_ns()

    def ejecutar_tarea(self,handle):
        gid=bytes(handle.goal_id.uuid).hex();res=ManipularObjeto.Result()
        with self.lock:p=self.por_goal_id[gid]
        inicio=time.monotonic();p.t_inicio_ejec=inicio
        res.wait_time_s=inicio-p.t_llegada;self.inicio_movimiento_wall_ns=0;self.referencia_movimiento=None
        self.evento('INICIO',p,wait_time_s=res.wait_time_s)
        try:
            if self.config['modo']=='simulado':backend=BackendSimulado(self.config)
            else:
                from .backend_ros import BackendReal
                backend=BackendReal(self,self.config)
            def feedback(etapa):
                fb=ManipularObjeto.Feedback();fb.state=etapa.upper();fb.queue_position=0
                fb.elapsed_s=time.monotonic()-inicio;handle.publish_feedback(fb)
            resultado=ejecutar(de_msg(handle.request.decision),backend,self.config,
                               lambda:handle.is_cancel_requested or self._parar.is_set(),feedback)
            res.success=resultado.exito;res.simulado=resultado.simulado;res.message=resultado.motivo
            res.error_fk_mm=resultado.error_fk_mm;res.q_medida_rad=resultado.q_medida_rad
            res.solicitado_xyz_m=resultado.solicitado_xyz_m
            res.inicio_comando_wall_ns=resultado.inicio_comando_wall_ns
            res.inicio_movimiento_wall_ns=resultado.inicio_movimiento_wall_ns
            res.preparacion_s=resultado.preparacion_s;res.gripper_previo_s=resultado.gripper_previo_s
            for campo,etapa in [('percepcion_s','percepcion'),('ik_s','cinematica_inversa'),
                                ('planificacion_s','planificacion'),('gripper_s','gripper'),('movimiento_s','movimiento')]:
                setattr(res,campo,resultado.etapas_s.get(etapa,0.0))
            with self.lock:
                with self.archivo_tareas.open('a',encoding='utf-8') as f:
                    f.write(json.dumps(dict(request_id=handle.request.request_id,client_id=p.client_id,
                                            frase=handle.request.frase,decision=de_msg(handle.request.decision).dict(),
                                            wait_time_s=res.wait_time_s,**asdict(resultado)),ensure_ascii=False)+'\n')
            if handle.is_cancel_requested:handle.canceled()
            elif res.success:
                handle.succeed()
                with self.lock:self.n_completados+=1
            else:handle.abort()
        except Exception as exc:
            res.success=False;res.simulado=self.config['modo']=='simulado';res.message=str(exc)
            if handle.is_active:handle.abort()
        finally:
            res.exec_time_s=time.monotonic()-inicio
            estado='CANCELADO' if handle.is_cancel_requested else ('COMPLETADO' if res.success else 'ERROR')
            self.evento(estado,p,motivo=res.message,wait_time_s=res.wait_time_s,exec_time_s=res.exec_time_s)
            p.fin.set()
        return res


def main():
    rclpy.init();nodo=None;ex=MultiThreadedExecutor(num_threads=6)
    try:
        nodo=BrokerParcial();ex.add_node(nodo);ex.spin()
    except KeyboardInterrupt:pass
    finally:
        if nodo:nodo._parar.set()
        ex.shutdown()
        if nodo:nodo.destroy_node()
        if rclpy.ok():rclpy.shutdown()
