"""Backend real compartido: solo el worker del broker publica al driver y acciona la pinza.

No importa MoveIt. BackendArticular planifica en espacio articular con las poses enseñadas;
backend_ros.BackendReal hereda de aquí y sustituye IK/planificación por MoveIt.
"""
import json
import time
from arm_broker_interfaces.srv import LocalizarObjeto, AccionarPinza
from .modelos import Pose, FalloTarea, Cancelado
from .ros_util import llamar
from .posiciones import comprobar_busqueda


class BackendBroker:
    simulado = False

    def __init__(self, broker, config):
        self.broker = broker; self.config = config; self.h = config['hardware']
        if not self.h.get('adaptador_serial_confirmado'):
            raise FalloTarea('Driver/adaptador serial pendiente de confirmar (hardware.adaptador_serial_confirmado)')
        if not config['camara'].get('calibracion_confirmada'):
            raise FalloTarea('Regiones de cámara pendientes de confirmar (camara.calibracion_confirmada)')
        self.inicio_movimiento_wall_ns = 0
        self.primer_comando_wall_ns = 0; self.posicion_id = ''; self.mapa_colores = {}
        self.percepcion = broker.cli_percepcion; self.gripper = broker.cli_pinza

    def estado(self):
        with self.broker.lock:
            q = self.broker.estado.q_medida
            t = self.broker.estado.t_medida
            if q is None or time.monotonic() - t > self.broker.estado.edad_max:
                raise FalloTarea('Falta estado articular medido reciente')
            return list(q)

    def localizar(self, d):
        req = LocalizarObjeto.Request(); req.objeto = d.objeto; req.color = d.color
        res = llamar(self.percepcion, req, self.h['timeout_servicio_s'])
        if not res.encontrado: raise FalloTarea(res.motivo)
        self.posicion_id = res.posicion_id
        try: self.mapa_colores = json.loads(res.mapa_colores_json)
        except (ValueError, TypeError) as exc: raise FalloTarea('Mapa de colores inválido') from exc
        p = res.pose.pose
        return Pose([p.position.x, p.position.y, p.position.z],
                    [p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w], res.pose.header.frame_id)

    def ejecutar(self, plan, cancelado):
        t0 = time.monotonic(); actual = self.estado()
        if max(abs(a - b) for a, b in zip(actual, plan[0][1])) > self.h['tolerancia_inicio_rad']:
            raise FalloTarea('La postura cambió después de planificar; volver a solicitar tarea')
        self.broker.referencia_movimiento = list(actual)
        for instante, q in plan:
            while time.monotonic() - t0 < instante:
                if cancelado(): raise Cancelado('Cancelado antes de un punto de trayectoria')
                time.sleep(min(0.01, max(0, instante - (time.monotonic() - t0))))
            if cancelado(): raise Cancelado('Cancelado durante trayectoria')
            if self.broker.pub_joint.get_subscription_count() == 0:
                raise FalloTarea('No hay driver suscrito al tópico de comandos')
            if not self.primer_comando_wall_ns: self.primer_comando_wall_ns = time.time_ns()
            self.broker.mover(q)
            self.inicio_movimiento_wall_ns = self.broker.inicio_movimiento_wall_ns
        fin = time.monotonic() + self.h['timeout_llegada_s']
        while time.monotonic() < fin:
            if cancelado(): raise Cancelado('Cancelado esperando posición medida')
            if max(abs(a - b) for a, b in zip(self.estado(), plan[-1][1])) <= self.h['tolerancia_llegada_rad']:
                self.inicio_movimiento_wall_ns = self.broker.inicio_movimiento_wall_ns
                return
            time.sleep(0.02)
        raise FalloTarea('El robot no confirmó la postura final a tiempo')

    def esperar_busqueda(self, cancelado):
        b = self.config['manipulacion']['busqueda']; fin = time.monotonic() + b['timeout_llegada_s']
        estable = None
        while time.monotonic() < fin:
            if cancelado(): raise Cancelado('Cancelado esperando búsqueda')
            try: comprobar_busqueda(self.estado(), self.config)
            except FalloTarea: estable = None
            else:
                if estable is None: estable = time.monotonic()
                if time.monotonic() - estable >= b['asentamiento_s']: return
            time.sleep(.02)
        raise FalloTarea('No se confirmó postura de búsqueda estable')

    def pinza(self, abierta, cancelado):
        req = AccionarPinza.Request(); req.abrir = abierta; req.timeout_s = self.h['timeout_pinza_s']
        res = llamar(self.gripper, req, self.h['timeout_pinza_s'] + 1, cancelado)
        if not res.completado: raise FalloTarea(res.motivo)


class BackendArticular(BackendBroker):
    """IK = poses articulares enseñadas; planificación = interpolación articular verificada con FK."""

    def __init__(self, broker, config):
        super().__init__(broker, config)
        from .posiciones import validar_articular
        validar_articular(config, real=True)

    def planificar(self, inicio, final):
        from .articular import interpolar
        paso = min(float(self.h['paso_plan_rad']), self.broker.estado.paso_max)
        return interpolar(list(inicio), list(final), paso, float(self.h['velocidad_articular_rad_s']))


def crear_backend(broker, config):
    """Fábrica usada por broker_parcial en modo real."""
    from .posiciones import usa_articular
    if usa_articular(config):
        return BackendArticular(broker, config)
    from .backend_ros import BackendReal
    return BackendReal(broker, config)
