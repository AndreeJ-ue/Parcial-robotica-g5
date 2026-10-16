""" Cliente de la pinza del JetCobot (GripperCommand) — Pregunta 2 """

""" El broker mueve poses pero NO controla la pinza: la pinza se comanda con la acción estándar
control_msgs/action/GripperCommand que se ASUME expone el driver/controlador del kit. Este
módulo es lo único que sabe cómo abrir y cerrar; el orquestador solo llama a abrir()/cerrar().

OJO: a diferencia del brazo (ver PARCHE_COMPENSACION_MOTOR.md, ya confirmado y arreglado),
esto NO está confirmado todavía. `ros2 node info /control_sync_plan` (el único nodo del driver
visible hasta ahora) no expone NINGÚN Action Server — así que 'gripper_command' como
GripperCommand casi seguro no vive ahí. Puede ser: (a) otro nodo del driver que no hemos visto
porque no estaba corriendo al hacer `ros2 node list`, (b) un tópico/servicio distinto (no una
acción), o (c) simplemente no expuesto por ROS y solo controlable con pymycobot directo (como en
docs/agarrar_cubo_sin_rastreo.py). Diagnóstico, con TODO el driver arriba:
    ros2 node list                    # ¿hay más nodos del driver aparte de control_sync_plan?
    ros2 action list -t | grep -i grip
    ros2 topic list | grep -i grip
    ros2 service list | grep -i grip
Si no aparece nada, usa 'gripper_habilitada:=false' en orquestador_item2 (ver README) para
demostrar el resto de la cadena mientras se resuelve la interfaz real de la pinza.

Las posiciones (abierto/cerrado) y el esfuerzo dependen del controlador: se calibran con
herramientas/probar_pinza.py """

import threading
import time

from control_msgs.action import GripperCommand
from rclpy.action import ActionClient


class Pinza:
    """Envoltura del ActionClient de GripperCommand con espera por evento (segura con
    MultiThreadedExecutor: los callbacks corren en otros hilos)"""

    def __init__(self, nodo, accion='gripper_command', abierto=0.0, cerrado=0.04,
                 esfuerzo=50.0, timeout=5.0):
        self.nodo = nodo
        self.accion = accion
        self.cli = ActionClient(nodo, GripperCommand, accion)
        self.abierto = float(abierto)
        self.cerrado = float(cerrado)
        self.esfuerzo = float(esfuerzo)
        self.timeout = float(timeout)
        self._aviso_dado = False

    def _esperar(self, futuro, timeout):
        evento = threading.Event()
        futuro.add_done_callback(lambda _: evento.set())
        if not evento.wait(timeout):
            return None
        return futuro.result()

    def _comandar(self, posicion):
        if not self.cli.wait_for_server(timeout_sec=self.timeout):
            if not self._aviso_dado:
                self._aviso_dado = True
                self.nodo.get_logger().error(
                    f"⚠️  la acción de la pinza '{self.accion}' no aparece tras {self.timeout:.0f}s. "
                    f"Con el driver arriba, revisa: `ros2 node list` (¿hay un nodo de pinza aparte "
                    f"de control_sync_plan?), `ros2 action list -t | grep -i grip`, "
                    f"`ros2 topic list | grep -i grip`, `ros2 service list | grep -i grip`. "
                    f"Mientras se resuelve, lanza el orquestador con -p gripper_habilitada:=false "
                    f"para demostrar el resto de la cadena sin bloquear cada intento aquí.")
            return False
        goal = GripperCommand.Goal()
        # ROS 2: el Goal no tiene 'position' directo; va dentro de 'command'
        # (control_msgs/msg/GripperCommand => position + max_effort)
        goal.command.position = float(posicion)
        goal.command.max_effort = self.esfuerzo
        envio = self.cli.send_goal_async(goal)
        handle = self._esperar(envio, self.timeout)
        if handle is None or not handle.accepted:
            self.nodo.get_logger().warn('la pinza rechazó el goal')
            return False
        self._esperar(handle.get_result_async(), self.timeout)
        return True

    def abrir(self):
        self.nodo.get_logger().info(f'🖐  pinza abrir ({self.abierto})')
        ok = self._comandar(self.abierto)
        time.sleep(0.5)
        return ok

    def cerrar(self):
        self.nodo.get_logger().info(f'✊ pinza cerrar ({self.cerrado})')
        ok = self._comandar(self.cerrado)
        time.sleep(0.5)
        return ok
