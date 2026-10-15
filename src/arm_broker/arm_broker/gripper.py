""" Pinza del JetCobot — Ítem 2 """

""" Vía PRIMARIA: la acción `gripper_command` (control_msgs/action/GripperCommand), cuyo goal
lleva `command.position`. Si esa acción no responde (el driver del kit no siempre la expone), se
cae a la vía serie de pinza_pymycobot.py. Con -p gripper_habilitada:=false la pinza no se toca
(modo solo-brazo) y el resto de la cadena sigue funcionando.

La pinza NO pasa por el broker: este es un comando local de garra, no un goal move_arm. La regla
dura se mantiene: el orquestador nunca publica /joint_states. """

import threading
import time

from rclpy.action import ActionClient

try:
    from control_msgs.action import GripperCommand
    CONTROL_MSGS_DISPONIBLE = True
except ImportError:
    CONTROL_MSGS_DISPONIBLE = False

from arm_broker import pinza_pymycobot


class Pinza:

    def __init__(self, nodo, habilitada=True, accion='gripper_command',
                 pos_abierta=100.0, pos_cerrada=0.0, esfuerzo=10.0,
                 timeout_accion_s=2.0, timeout_resultado_s=5.0,
                 usar_pymycobot_si_falla=True, puerto='/dev/ttyUSB0',
                 baudios=1000000, velocidad=50):
        self.nodo = nodo
        self.habilitada = bool(habilitada)
        self.nombre_accion = str(accion)
        self.pos_abierta = float(pos_abierta)
        self.pos_cerrada = float(pos_cerrada)
        self.esfuerzo = float(esfuerzo)
        self.timeout_accion_s = float(timeout_accion_s)
        self.timeout_resultado_s = float(timeout_resultado_s)
        self.usar_pymycobot_si_falla = bool(usar_pymycobot_si_falla)
        self.puerto = puerto
        self.baudios = baudios
        self.velocidad = velocidad

        self.via = None
        self.cliente = None
        self.serie = None
        self._descubierto = False
        self.lock = threading.Lock()

    # 1. Descubrimiento de la vía (perezoso: se hace con el executor ya girando)
    def _descubrir(self):
        if self._descubierto:
            return
        with self.lock:
            if self._descubierto:
                return
            self._descubierto = True

            if not self.habilitada:
                self.nodo.get_logger().info('[PINZA] deshabilitada por parámetro')
                return

            if CONTROL_MSGS_DISPONIBLE:
                self.cliente = ActionClient(self.nodo, GripperCommand, self.nombre_accion)
                if self.cliente.wait_for_server(timeout_sec=self.timeout_accion_s):
                    self.via = 'command'
                    self.nodo.get_logger().info(
                        f"[PINZA] vía PRIMARIA lista: acción '{self.nombre_accion}'")
                    return
                self.nodo.get_logger().warn(
                    f"[PINZA] la acción '{self.nombre_accion}' no responde")

            if self.usar_pymycobot_si_falla:
                self.serie = pinza_pymycobot.PinzaPymycobot(
                    puerto=self.puerto, baudios=self.baudios, velocidad=self.velocidad,
                    abierta=int(self.pos_abierta), cerrada=int(self.pos_cerrada))
                if self.serie.disponible:
                    self.via = 'pymycobot'
                    self.nodo.get_logger().info('[PINZA] vía de respaldo: pymycobot')
                    return

            self.nodo.get_logger().warn(
                '[PINZA] sin vía disponible: el agarre no cerrará la pinza')

    # 2. API del orquestador
    def abrir(self):
        return self.enviar(self.pos_abierta)

    def cerrar(self):
        return self.enviar(self.pos_cerrada)

    def enviar(self, posicion):
        """Lleva la pinza a la posición pedida por la vía activa."""
        if not self.habilitada:
            return True
        self._descubrir()
        if self.via == 'command':
            return self._por_accion(posicion)
        if self.via == 'pymycobot':
            return self.serie.abrir() if posicion >= 50 else self.serie.cerrar()
        return False

    # 3. Vía primaria: acción gripper_command
    def _por_accion(self, posicion):
        meta = GripperCommand.Goal()
        meta.command.position = float(posicion)
        meta.command.max_effort = self.esfuerzo

        envio = self.cliente.send_goal_async(meta)
        if not self._esperar(envio):
            self.nodo.get_logger().warn('[PINZA] la acción no aceptó el goal de pinza')
            return False
        handle = envio.result()
        if handle is None or not handle.accepted:
            return False

        resultado = handle.get_result_async()
        if not self._esperar(resultado, self.timeout_resultado_s):
            self.nodo.get_logger().warn('[PINZA] la acción no devolvió resultado de pinza')
            return False
        r = resultado.result().result
        return bool(getattr(r, 'reached_goal', True) or getattr(r, 'stalled', False))

    @staticmethod
    def _esperar(futuro, timeout_s=3.0):
        """Espera un futuro mientras el executor del nodo sigue girando en otro hilo."""
        t0 = time.time()
        while not futuro.done():
            if time.time() - t0 > timeout_s:
                return False
            time.sleep(0.02)
        return True
