""" Nodo de pinza del JetCobot controlado con pymycobot — Pregunta 2

El driver del kit (`sync_plan_nx` / nodo `control_sync_plan`) SOLO escucha `/joint_states`
y NO expone una acción de pinza (ver `docs/grados/PINZA_NO_SE_MUEVE.md`). Por eso el
orquestador no encontraba `gripper_command`.

Este nodo SÍ expone la acción estándar `control_msgs/action/GripperCommand` y por dentro
llama a `set_gripper_value()` de pymycobot usando la escala del kit (0..100), que es la
misma que usaba el script probado `item2/5.py`:
    ABRIR  -> 100
    CERRAR ->  15

Escala: el `goal.command.position` se interpreta DIRECTAMENTE en 0..100.
  Lanza el orquestador con:  -p gripper_abierto:=100 -p gripper_cerrado:=15

OJO (léelo antes de la demo): el driver del brazo abre el puerto serie `/dev/ttyUSB0`.
Un segundo `MyCobot(...)` sobre el MISMO puerto puede fallar o competir con el driver.
Comprueba en la Jetson quién tiene el puerto (ver `PINZA_NO_SE_MUEVE.md` §4). Si no se
puede compartir, demuestra el resto de la cadena con `-p gripper_habilitada:=false` en el
orquestador y deja este nodo para cuando el reparto del puerto esté resuelto.

Regla del RB-2: este nodo NO publica `/joint_states` (la regla del publicador único
aplica SOLO a ese tópico), así que no anula el puntaje de la Pregunta 2.
"""

import threading
import time

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from control_msgs.action import GripperCommand

try:
    from pymycobot.mycobot import MyCobot
except ImportError:  # pymycobot solo existe en la Jetson
    MyCobot = None


class PinzaPymycobot(Node):

    def __init__(self):
        super().__init__('pinza_pymycobot')

        self.declare_parameter('puerto', '/dev/ttyUSB0')
        self.declare_parameter('baudios', 1000000)
        self.declare_parameter('velocidad', 50)          # GRIPPER_VEL del 5.py
        self.declare_parameter('accion', 'gripper_command')
        self.declare_parameter('segundos_asentado', 1.5)  # pausa del script original

        self.puerto = str(self.get_parameter('puerto').value)
        self.baudios = int(self.get_parameter('baudios').value)
        self.velocidad = int(self.get_parameter('velocidad').value)
        self.segundos = float(self.get_parameter('segundos_asentado').value)

        if MyCobot is None:
            raise RuntimeError(
                'pymycobot no está instalado en este entorno. Instálalo en la Jetson '
                '(`pip3 install pymycobot --break-system-packages`) o usa '
                'gripper_habilitada:=false en el orquestador.')

        self.robot = None
        self.lock = threading.Lock()

        self.servidor = ActionServer(
            self,
            GripperCommand,
            str(self.get_parameter('accion').value),
            goal_callback=self._goal_callback,
            cancel_callback=lambda _: CancelResponse.ACCEPT,
            execute_callback=self._execute_callback,
            callback_group=ReentrantCallbackGroup(),
        )

        self.get_logger().info(
            f'pinza_pymycobot lista · acción={self.get_parameter("accion").value} · '
            f'puerto={self.puerto} · escala 0..100 (abrir=100, cerrar=15)')

    # 1. Conexión perezosa: no abrimos el puerto serie hasta el primer goal
    def _robot(self):
        if self.robot is None:
            self.get_logger().info(f'abriendo {self.puerto} @ {self.baudios} ...')
            try:
                self.robot = MyCobot(self.puerto, self.baudios)
            except Exception as e:
                self.get_logger().error(
                    f'no se pudo abrir {self.puerto}: {e!r} · comprueba con '
                    f'`ls -l /dev/serial/by-id/` y `fuser -v {self.puerto}` '
                    f'(¿lo tiene el driver sync_plan_nx?)')
                raise
        return self.robot

    # 2. Admisión: valida el rango 0..100 antes de aceptar el goal
    def _goal_callback(self, goal_request):
        # ROS 2: el Goal trae un 'command' (control_msgs/msg/GripperCommand)
        posicion = float(goal_request.command.position)
        if not 0.0 <= posicion <= 100.0:
            self.get_logger().error(
                f'goal RECHAZADO: position={posicion} fuera de la escala del kit 0..100')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    # 3. Ejecución: traduce 0..100 -> set_gripper_value(0..100, velocidad)
    def _execute_callback(self, goal_handle):
        # ROS 2: el Goal trae un 'command' (control_msgs/msg/GripperCommand)
        posicion = float(goal_handle.request.command.position)   # 0..100 (escala del kit)
        resultado = GripperCommand.Result()
        try:
            with self.lock:  # el puerto serie no admite dos escrituras a la vez
                self._robot().set_gripper_value(int(round(posicion)), self.velocidad)
                time.sleep(self.segundos)
            resultado.position = posicion
            resultado.reached_goal = True
            resultado.stalled = False
            goal_handle.succeed()
            self.get_logger().info(f'🖐  pinza -> {posicion:.0f} (vel {self.velocidad})')
        except Exception as e:
            # Rellenar el Result para que no salga un 0.0/aborted engañoso
            resultado.position = 0.0
            resultado.stalled = True
            resultado.reached_goal = False
            self.get_logger().error(
                f'fallo comandando la pinza: {e!r} · comprueba el puerto con '
                f'`fuser -v {self.puerto}` (¿lo tiene el driver sync_plan_nx?)')
            goal_handle.abort()
        return resultado


def main(args=None):
    rclpy.init(args=args)
    nodo = PinzaPymycobot()
    ejecutor = MultiThreadedExecutor(num_threads=2)
    ejecutor.add_node(nodo)
    try:
        ejecutor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
