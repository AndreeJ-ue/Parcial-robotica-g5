"""Ruta MoveIt: IK y planificación con MoveIt2; la ejecución la hace el worker del broker.

Requiere el grupo MoveIt del JetCobot. Sin MoveIt usar manipulacion.ejecucion="articular"
(backend_broker.BackendArticular).
"""
import math
from arm_broker import fk
from moveit_msgs.srv import GetPositionIK,GetMotionPlan
from moveit_msgs.msg import Constraints,JointConstraint
from geometry_msgs.msg import PoseStamped
from .modelos import FalloTarea
from .ros_util import llamar
from .posiciones import usa_posiciones, validar
from .backend_broker import BackendBroker


class BackendReal(BackendBroker):
    def __init__(self,broker,config):
        super().__init__(broker,config)
        obligatorios=('modelo_confirmado','driver_trayectorias_validado','escena_colisiones_confirmada')
        if not all(self.h.get(k) for k in obligatorios):
            raise FalloTarea('Modelo MoveIt, driver de trayectoria o escena pendientes de confirmar')
        if not usa_posiciones(config):raise FalloTarea('Estrategia de manipulación no soportada')
        validar(config,real=True)
        if len(self.h['joint_names_moveit'])!=6 or not self.h['grupo_moveit'] or not self.h['eef_link']:
            raise FalloTarea('Faltan grupo, efector o seis nombres del modelo MoveIt')
        if not hasattr(broker,'cli_ik') or not hasattr(broker,'cli_plan'):
            raise FalloTarea('El broker no creó clientes MoveIt (manipulacion.ejecucion debe ser moveit)')
        self.ik_cli=broker.cli_ik; self.plan_cli=broker.cli_plan
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
