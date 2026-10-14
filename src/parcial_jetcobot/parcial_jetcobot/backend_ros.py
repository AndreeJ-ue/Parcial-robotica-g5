"""MoveIt planifica; solo la ejecución autorizada por el worker publica al driver."""
import math
import time
from arm_broker import fk
from arm_broker_interfaces.srv import LocalizarObjeto,AccionarPinza
from moveit_msgs.srv import GetPositionIK,GetMotionPlan
from moveit_msgs.msg import Constraints,JointConstraint
from geometry_msgs.msg import PoseStamped
from .modelos import Pose,FalloTarea,Cancelado
from .ros_util import llamar


class BackendReal:
    simulado=False
    def __init__(self,broker,config):
        self.broker=broker; self.config=config; self.h=config['hardware']
        obligatorios=('modelo_confirmado','driver_trayectorias_validado','adaptador_serial_confirmado','escena_colisiones_confirmada')
        if not all(self.h.get(k) for k in obligatorios):
            raise FalloTarea('Modelo, driver de trayectoria o adaptador serial pendientes de confirmar')
        if not config.get('catalogo_confirmado') or not config['camara'].get('calibracion_confirmada') or not config['camara'].get('camara_fija'):
            raise FalloTarea('Catálogo y cámara pendientes de confirmar')
        if len(self.h['joint_names_moveit'])!=6 or not self.h['grupo_moveit'] or not self.h['eef_link']:
            raise FalloTarea('Faltan grupo, efector o seis nombres del modelo MoveIt')
        self.inicio_movimiento_wall_ns=0
        self.percepcion=broker.cli_percepcion; self.ik_cli=broker.cli_ik
        self.plan_cli=broker.cli_plan; self.gripper=broker.cli_pinza
    def estado(self):
        with self.broker.lock:
            q=self.broker.estado.q_medida
            t=self.broker.estado.t_medida
            if q is None or time.monotonic()-t>self.broker.estado.edad_max:
                raise FalloTarea('Falta estado articular medido reciente')
            return list(q)
    def localizar(self,d):
        req=LocalizarObjeto.Request();req.objeto=d.objeto;req.color=d.color
        res=llamar(self.percepcion,req,self.h['timeout_servicio_s'])
        if not res.encontrado:raise FalloTarea(res.motivo)
        p=res.pose.pose
        return Pose([p.position.x,p.position.y,p.position.z],
                    [p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w],res.pose.header.frame_id)
    def _pose(self,pose):
        pose.validar(); msg=PoseStamped();msg.header.frame_id=pose.frame_id
        msg.header.stamp=self.broker.get_clock().now().to_msg()
        msg.pose.position.x,msg.pose.position.y,msg.pose.position.z=pose.xyz_m
        q=msg.pose.orientation;q.x,q.y,q.z,q.w=pose.quaternion_xyzw
        return msg
    def ik(self,pose,semilla):
        req=GetPositionIK.Request(); r=req.ik_request
        r.group_name=self.h['grupo_moveit'];r.ik_link_name=self.h['eef_link']
        r.pose_stamped=self._pose(pose);r.avoid_collisions=True
        r.timeout.sec=int(self.h['timeout_ik_s']);r.timeout.nanosec=int((self.h['timeout_ik_s']%1)*1e9)
        r.robot_state.joint_state.name=self.h['joint_names_moveit']
        r.robot_state.joint_state.position=list(semilla);r.robot_state.is_diff=True
        res=llamar(self.ik_cli,req,self.h['timeout_servicio_s'])
        if res.error_code.val!=1:raise FalloTarea(f'IK falló: código {res.error_code.val}')
        por_nombre=dict(zip(res.solution.joint_state.name,res.solution.joint_state.position))
        try:q=[por_nombre[n] for n in self.h['joint_names_moveit']]
        except KeyError as exc:raise FalloTarea('Respuesta IK con articulaciones incompletas') from exc
        ok,motivo=fk.dentro_de_limites(q)
        if not ok:raise FalloTarea(motivo)
        return q
    def planificar(self,inicio,final):
        req=GetMotionPlan.Request(); r=req.motion_plan_request
        r.group_name=self.h['grupo_moveit'];r.num_planning_attempts=1
        r.allowed_planning_time=self.h['timeout_planificacion_s']
        r.max_velocity_scaling_factor=self.h['velocidad_escala']
        r.max_acceleration_scaling_factor=self.h['aceleracion_escala']
        r.start_state.joint_state.name=self.h['joint_names_moveit'];r.start_state.joint_state.position=list(inicio)
        r.start_state.is_diff=True
        constraints=Constraints()
        for nombre,posicion in zip(self.h['joint_names_moveit'],final):
            c=JointConstraint();c.joint_name=nombre;c.position=float(posicion)
            c.tolerance_above=c.tolerance_below=0.001;c.weight=1.0
            constraints.joint_constraints.append(c)
        r.goal_constraints=[constraints]
        res=llamar(self.plan_cli,req,self.h['timeout_servicio_s']).motion_plan_response
        if res.error_code.val!=1:raise FalloTarea(f'MoveIt falló: código {res.error_code.val}')
        tr=res.trajectory.joint_trajectory
        if not tr.points:raise FalloTarea('Trayectoria vacía')
        try:indices=[tr.joint_names.index(n) for n in self.h['joint_names_moveit']]
        except ValueError as exc:raise FalloTarea('Trayectoria con articulaciones incompletas') from exc
        plan=[];prev_t=-1.0;prev_q=list(inicio)
        for punto in tr.points:
            try:q=[punto.positions[i] for i in indices]
            except IndexError as exc:raise FalloTarea('Punto de trayectoria incompleto') from exc
            t=punto.time_from_start.sec+punto.time_from_start.nanosec/1e9
            ok,motivo=fk.dentro_de_limites(q)
            if ok:ok,motivo=fk.dentro_del_workspace(q)
            if not ok or not math.isfinite(t) or t<prev_t:
                raise FalloTarea('Trayectoria inválida: '+motivo)
            if fk.paso_articular(prev_q,q)>self.broker.estado.paso_max:
                raise FalloTarea('Trayectoria excede el paso máximo; adaptar resolución del plan')
            plan.append((t,q));prev_t=t;prev_q=q
        if plan[-1][0]<=0:raise FalloTarea('Trayectoria sin temporización')
        return plan
    def ejecutar(self,plan,cancelado):
        t0=time.monotonic();actual=self.estado()
        if max(abs(a-b) for a,b in zip(actual,plan[0][1]))>self.h['tolerancia_inicio_rad']:
            raise FalloTarea('La postura cambió después de planificar; volver a solicitar tarea')
        self.broker.referencia_movimiento=list(actual)
        for instante,q in plan:
            while time.monotonic()-t0<instante:
                if cancelado():raise Cancelado('Cancelado antes de un punto de trayectoria')
                time.sleep(min(0.01,max(0,instante-(time.monotonic()-t0))))
            if cancelado():raise Cancelado('Cancelado durante trayectoria')
            if self.broker.pub_joint.get_subscription_count()==0:
                raise FalloTarea('No hay driver suscrito al tópico de comandos')
            self.broker.mover(q)
        fin=time.monotonic()+self.h['timeout_llegada_s']
        while time.monotonic()<fin:
            if cancelado():raise Cancelado('Cancelado esperando posición medida')
            if max(abs(a-b) for a,b in zip(self.estado(),plan[-1][1]))<=self.h['tolerancia_llegada_rad']:
                self.inicio_movimiento_wall_ns=self.broker.inicio_movimiento_wall_ns
                return
            time.sleep(0.02)
        raise FalloTarea('El robot no confirmó la postura final a tiempo')
    def pinza(self,abierta,cancelado):
        req=AccionarPinza.Request();req.abrir=abierta;req.timeout_s=self.h['timeout_pinza_s']
        res=llamar(self.gripper,req,self.h['timeout_pinza_s']+1,cancelado)
        if not res.completado:raise FalloTarea(res.motivo)
