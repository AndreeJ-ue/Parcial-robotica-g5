"""Broker RB2: admisión atómica, cola y ejecución serializada.

Conserva MoveArm y QueueState del curso. SUCCEEDED confirma envío de comandos,
no precisión ni éxito físico; el driver del laboratorio debe verificarse aparte.
"""
import math
import threading
import time
import uuid

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState
from arm_broker_interfaces.action import MoveArm
from arm_broker_interfaces.msg import QueueState
from arm_broker import fk
from arm_broker.estado import EstadoAdmision
from arm_broker.eventos import RegistroEventos
from arm_broker.politicas import POLITICAS, Pedido


class ArmBroker(Node):
    def __init__(self):
        super().__init__('arm_broker')
        defaults = {'politica': 'fifo', 'tau_envejecimiento_s': 8.0,
                    'cola_max': 20, 'paso_max_rad': 1.2,
                    'duracion_movimiento_s': 3.0, 'pasos_interpolacion': 10,
                    'estado_inicial_confirmado': False, 'q_inicial_rad': [0.0] * 6,
                    'estado_medido_topic': '/arm/joint_states_measured',
                    'edad_max_estado_s': 2.0, 'archivo_eventos': ''}
        for nombre, valor in defaults.items():
            self.declare_parameter(nombre, valor)
        valor = lambda nombre: self.get_parameter(nombre).value
        nombre = valor('politica')
        if nombre not in POLITICAS:
            raise ValueError(f'política desconocida: {nombre}')
        tau = float(valor('tau_envejecimiento_s'))
        if not math.isfinite(tau):
            raise ValueError('tau_envejecimiento_s debe ser finito')
        self.politica = POLITICAS[nombre](tau) if nombre == 'prioridad' else POLITICAS[nombre]()
        self.duracion = float(valor('duracion_movimiento_s'))
        self.pasos = int(valor('pasos_interpolacion'))
        if not math.isfinite(self.duracion) or self.duracion <= 0 or self.pasos < 1:
            raise ValueError('duración y pasos deben ser positivos')
        q_inicial = list(valor('q_inicial_rad')) if valor('estado_inicial_confirmado') else None
        if q_inicial is not None:
            ok, motivo = fk.dentro_de_limites(q_inicial)
            if not ok:
                raise ValueError(f'q_inicial_rad: {motivo}')
        self.estado = EstadoAdmision(int(valor('cola_max')), float(valor('paso_max_rad')),
                                    q_inicial, float(valor('edad_max_estado_s')))
        self.lock = self.estado.lock
        self.pendientes = []
        self.por_goal_id = {}
        self.admisiones = {}  # request vivo -> llegada; conserva objeto hasta accepted
        self.ejecutando = None
        self.n_aceptados = self.n_rechazados = self.n_completados = 0
        self._parar = threading.Event()
        self.grupo_entrada = ReentrantCallbackGroup()
        self.grupo_worker = MutuallyExclusiveCallbackGroup()
        self.registro = RegistroEventos(valor('archivo_eventos'))
        self.pub_joint = self.create_publisher(JointState, '/joint_states', 10)
        self.pub_cola = self.create_publisher(QueueState, '/arm/queue_state', 10)
        topico = valor('estado_medido_topic')
        if topico == '/joint_states' or (topico and self.resolve_topic_name(topico) == '/joint_states'):
            raise ValueError('estado_medido_topic no puede ser el tópico de comandos /joint_states')
        self.sub_medida = self.create_subscription(JointState, topico, self.recibir_medida, 10,
                                                 callback_group=self.grupo_entrada) if topico else None
        self.servidor = ActionServer(self, MoveArm, 'move_arm',
                                    goal_callback=self.goal_callback,
                                    handle_accepted_callback=self.handle_accepted_callback,
                                    cancel_callback=self.cancel_callback,
                                    execute_callback=self.execute_callback,
                                    callback_group=self.grupo_entrada)
        self.create_timer(0.2, self.publicar_estado_cola, callback_group=self.grupo_worker)
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()
        self.get_logger().info(f'arm_broker listo · política={nombre} · cola_max={self.estado.capacidad}')
        if q_inicial is None:
            self.get_logger().warn('Postura inicial desconocida: se rechaza movimiento hasta recibir medida real.')
        else:
            self.get_logger().warn('Postura inicial confirmada por operador; no hay verificación física del movimiento.')

    def evento(self, evento, pedido=None, motivo='', req=None, **tiempos):
        try:
            self.registro.registrar(evento,
                                   goal_id=pedido.goal_id if pedido else 'rechazo-' + uuid.uuid4().hex,
                                   client_id=pedido.client_id if pedido else getattr(req, 'client_id', ''),
                                   priority=pedido.priority if pedido else getattr(req, 'priority', 0),
                                   motivo=motivo, **tiempos)
        except Exception as exc:
            self.get_logger().error(f'No se pudo registrar evidencia: {exc}')

    def recibir_medida(self, msg):
        if len(msg.name) != len(msg.position) or len(set(msg.name)) != len(msg.name):
            self.get_logger().warn('Estado medido inválido: nombres/posiciones inconsistentes')
            return
        por_nombre = dict(zip(msg.name, msg.position))
        if any(nombre not in por_nombre for nombre in fk.JOINT_NAMES):
            self.get_logger().warn('Estado medido incompleto: faltan articulaciones')
            return
        q = [por_nombre[nombre] for nombre in fk.JOINT_NAMES]
        ok, motivo = fk.dentro_de_limites(q)
        if not ok:
            self.get_logger().warn(f'Estado medido inválido: {motivo}')
            return
        self.estado.medir(q)

    def rechazar(self, req, motivo):
        with self.lock:
            self.n_rechazados += 1
        self.get_logger().warn(f'Goal rechazado: {motivo}')
        self.evento('RECHAZADO', req=req, motivo=motivo)
        return GoalResponse.REJECT

    # ====================== IMPLEMENTAR · ítem 2 ======================
    def goal_callback(self, req):
        q = list(req.joint_positions)
        for validar in (fk.dentro_de_limites, fk.dentro_del_workspace):
            ok, motivo = validar(q)
            if not ok:
                return self.rechazar(req, motivo)
        with self.lock:
            if self._parar.is_set():
                return self.rechazar(req, 'broker deteniéndose')
            ok, motivo = self.estado.reservar(q)
            if not ok:
                return self.rechazar(req, motivo)
            self.n_aceptados += 1
            self.admisiones[id(req)] = (req, time.monotonic(), self.n_aceptados)
        return GoalResponse.ACCEPT

    def handle_accepted_callback(self, handle):
        pedido = Pedido(handle, handle.request.client_id, handle.request.priority,
                        handle.request.joint_positions)
        with self.lock:
            _, pedido.t_llegada, pedido.secuencia = self.admisiones.pop(id(handle.request))
            self.pendientes.append(pedido)
            self.pendientes.sort(key=lambda p: p.secuencia)
            self.por_goal_id[pedido.goal_id] = pedido
            self.evento('ACEPTADO', pedido)
        # No se ejecuta aquí. La capacidad ya fue reservada en goal_callback.

    def _worker(self):
        while not self._parar.is_set():
            pedido = None
            with self.lock:
                if self.ejecutando is None and self.pendientes:
                    # Cancelaciones en espera se finalizan sin esperar su prioridad.
                    idx = next((i for i, p in enumerate(self.pendientes)
                                if p.goal_handle.is_cancel_requested), None)
                    if idx is None:
                        idx = self.politica.siguiente(self.pendientes)
                        if self.politica.nombre == 'fifo' and idx is not None and any(
                                admision[2] < self.pendientes[idx].secuencia
                                for admision in self.admisiones.values()):
                            idx = None  # esperar accepted callback del pedido anterior
                    if idx is not None:
                        pedido = self.pendientes.pop(idx)
                        self.estado.liberar()
                        self.ejecutando = pedido
            if pedido is None:
                self._parar.wait(0.05)
                continue
            try:
                # También los cancelados pasan por callback para devolver Result.
                pedido.goal_handle.execute()
                while not pedido.fin.wait(0.05):
                    if self._parar.is_set():
                        break
            except Exception as exc:
                self.get_logger().error(f'No se pudo iniciar el pedido: {exc}')
                if pedido.goal_handle.is_active:
                    pedido.goal_handle.abort()
                self.evento('ERROR', pedido, motivo=str(exc))
            finally:
                with self.lock:
                    self.ejecutando = None
                    self.por_goal_id.pop(pedido.goal_id, None)
                self.politica.atendido(pedido)

    def execute_callback(self, handle):
        goal_id = bytes(handle.goal_id.uuid).hex()
        with self.lock:
            pedido = self.por_goal_id.get(goal_id)
        res = MoveArm.Result()
        if pedido is None:
            res.success = False
            res.message = 'Pedido no encontrado'
            handle.abort()
            return res
        inicio = time.monotonic()
        res.wait_time_s = inicio - pedido.t_llegada
        terminado = 'ERROR'
        try:
            if handle.is_cancel_requested:
                terminado = 'CANCELADO'
                res.message = 'Cancelado antes de publicar comandos'
                handle.canceled()
                return res
            if self._parar.is_set():
                raise RuntimeError('broker deteniéndose')
            with self.lock:
                # Revalidar al ejecutar: la postura pudo cambiar mientras esperaba.
                ok, motivo = self.estado.validar_paso(pedido.joint_positions)
                q_inicio, _ = self.estado.referencia()
            if not ok:
                raise RuntimeError(motivo)
            if self.pub_joint.get_subscription_count() == 0:
                raise RuntimeError('sin suscriptor en /joint_states; verificar driver')
            pedido.t_inicio_ejec = inicio
            self.evento('INICIO', pedido, wait_time_s=res.wait_time_s)
            for paso in range(1, self.pasos + 1):
                if handle.is_cancel_requested or self._parar.is_set():
                    break
                frac = paso / self.pasos
                q = [a + frac * (b - a) for a, b in zip(q_inicio, pedido.joint_positions)]
                self.mover(q)
                fb = MoveArm.Feedback()
                fb.state, fb.queue_position = 'EXECUTING', 0
                fb.elapsed_s = time.monotonic() - inicio
                handle.publish_feedback(fb)
                self._parar.wait(self.duracion / self.pasos)
            if handle.is_cancel_requested:
                terminado = 'CANCELADO'
                res.message = 'Envío interrumpido; confirmar parada física con el driver'
                handle.canceled()
            elif self._parar.is_set():
                raise RuntimeError('broker detenido durante el envío')
            else:
                terminado = 'COMPLETADO'
                res.success = True
                res.message = 'Comandos enviados; movimiento físico no verificado'
                handle.succeed()
                with self.lock:
                    self.n_completados += 1
        except Exception as exc:
            res.success = False
            res.message = str(exc)
            self.get_logger().error(f'Pedido {goal_id}: {exc}')
            if handle.is_active:
                handle.abort()
        finally:
            res.exec_time_s = time.monotonic() - inicio if pedido.t_inicio_ejec is not None else 0.0
            self.evento(terminado, pedido, motivo=res.message,
                        wait_time_s=res.wait_time_s, exec_time_s=res.exec_time_s)
            pedido.fin.set()
        return res
    # ==================================================================

    def cancel_callback(self, handle):
        return CancelResponse.ACCEPT

    def mover(self, q):
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        msg.name = fk.JOINT_NAMES
        msg.position = [float(v) for v in q]
        self.pub_joint.publish(msg)
        self.estado.ordenar(q)

    def publicar_estado_cola(self):
        msg = QueueState()
        msg.stamp = self.get_clock().now().to_msg()
        with self.lock:
            ej = self.ejecutando
            msg.executing_client = ej.client_id if ej else ''
            msg.executing_goal_id = ej.goal_id if ej else ''
            msg.executing_elapsed_s = (time.monotonic() - ej.t_inicio_ejec
                                      if ej and ej.t_inicio_ejec is not None else 0.0)
            cola = list(self.pendientes)
            msg.queue_length = len(cola)
            msg.queued_goal_ids = [p.goal_id for p in cola]
            msg.queued_clients = [p.client_id for p in cola]
            msg.queued_priorities = [p.priority for p in cola]
            msg.queued_wait_s = [p.espera_s for p in cola]
            msg.total_accepted, msg.total_rejected = self.n_aceptados, self.n_rechazados
            msg.total_completed = self.n_completados
        self.pub_cola.publish(msg)
        for posicion, p in enumerate(cola, 1):
            if p.goal_handle.is_cancel_requested:
                continue
            # La extensión del parcial comparte este worker y usa su propia acción.
            fb = getattr(p, 'feedback_factory', MoveArm.Feedback)()
            fb.state, fb.queue_position, fb.elapsed_s = 'QUEUED', posicion, p.espera_s
            try:
                p.goal_handle.publish_feedback(fb)
            except Exception as exc:
                self.get_logger().debug(f'Feedback no disponible: {exc}')

    def destroy_node(self):
        self._parar.set()
        self.worker.join(timeout=2.0)
        self.registro.cerrar()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    nodo = None
    executor = MultiThreadedExecutor()
    try:
        nodo = ArmBroker()
        executor.add_node(nodo)
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        if nodo:
            nodo._parar.set()
        executor.shutdown()
        if nodo:
            nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
