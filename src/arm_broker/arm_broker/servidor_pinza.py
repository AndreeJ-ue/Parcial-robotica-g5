""" Servidor de la pinza del JetCobot: expone la acción estándar gripper_command — Ítem 2 """

""" El orquestador manda los pasos de pinza con abrir()/cerrar() (ver gripper.py), que usan la
acción `control_msgs/action/GripperCommand`. El driver del kit (sync_plan_nx) NO ofrece esa
acción: solo traduce /joint_states al brazo. Por eso aquí levantamos el servidor que SÍ falta,
apoyado en pymycobot sobre el puerto serie del kit.

`command.position` se interpreta en la escala del kit (0..100): 100 = abierta, 15 = cerrada
(poses.GRIPPER_ABIERTO / poses.GRIPPER_CERRADO). El trabajo serie lo hace el envoltorio
pinza_pymycobot.PinzaPymycobot, para no duplicar el trato con pymycobot.

Aviso importante: el driver del brazo y este nodo comparten /dev/ttyUSB0. Si el driver retiene el
puerto, la apertura fallará (se registra el motivo). Comprueba quién lo tiene en la Jetson:
    fuser -v /dev/ttyUSB0        # ¿lo tiene sync_plan_nx?
    ls -l /dev/serial/by-id/     # nombre estable del dispositivo
Mientras se resuelve el reparto del puerto, la demo puede correr con
`-p gripper_habilitada:=false` en el orquestador (el resto de la cadena sigue igual).

Este nodo NO publica /joint_states, así que no rompe la regla del publicador único. """

import threading

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from control_msgs.action import GripperCommand

from arm_broker import pinza_pymycobot


class ServidorPinza(Node):

    def __init__(self):
        super().__init__('servidor_pinza')

        self.declare_parameter('puerto', '/dev/ttyUSB0')
        self.declare_parameter('baudios', 1000000)
        self.declare_parameter('velocidad', 50)          # GRIPPER_SPEED del script probado
        self.declare_parameter('accion', 'gripper_command')

        self.puerto = str(self.get_parameter('puerto').value)
        self.baudios = int(self.get_parameter('baudios').value)
        self.velocidad = int(self.get_parameter('velocidad').value)
        self.nombre_accion = str(self.get_parameter('accion').value)

        self.garra = None
        self.lock = threading.Lock()

        self.servidor = ActionServer(
            self,
            GripperCommand,
            self.nombre_accion,
            goal_callback=self._al_proponer_meta,
            cancel_callback=lambda _: CancelResponse.ACCEPT,
            execute_callback=self._al_ejecutar,
            callback_group=ReentrantCallbackGroup(),
        )

        self.get_logger().info('=' * 60)
        self.get_logger().info('  SERVIDOR_PINZA LISTO (acción gripper_command)')
        self.get_logger().info(f'  acción : {self.nombre_accion}')
        self.get_logger().info(f'  puerto : {self.puerto} @ {self.baudios}')
        self.get_logger().info('  escala : 0..100 (abrir=100, cerrar=15)')
        self.get_logger().info('=' * 60)

    # 1. Apertura perezosa: el puerto se abre con el primer goal, no al arrancar
    def _garra_lista(self):
        if self.garra is None:
            self.get_logger().info(f'abriendo {self.puerto} @ {self.baudios} ...')
            self.garra = pinza_pymycobot.PinzaPymycobot(
                puerto=self.puerto, baudios=self.baudios, velocidad=self.velocidad)
            if not self.garra.disponible:
                self.get_logger().error(
                    f'no pude abrir {self.puerto}: revisa `fuser -v {self.puerto}` (¿lo tiene '
                    f'el driver sync_plan_nx?) y `ls -l /dev/serial/by-id/`')
        return self.garra.disponible

    # 2. Admisión de la meta: se acepta solo si la posición cae en la escala 0..100
    def _al_proponer_meta(self, meta):
        posicion = float(meta.command.position)
        if not 0.0 <= posicion <= 100.0:
            self.get_logger().error(
                f'meta RECHAZADA: position={posicion} fuera de la escala 0..100')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    # 3. Ejecución: se traduce la posición a set_gripper_value() con el envoltorio serie
    def _al_ejecutar(self, meta_handle):
        posicion = float(meta_handle.request.command.position)
        resultado = GripperCommand.Result()
        with self.lock:                              # el puerto serie no admite dos escrituras
            listo = self._garra_lista()
            movido = listo and self.garra.ir_a(posicion)

        if movido:
            resultado.position = posicion
            resultado.effort = 0.0
            resultado.stalled = False
            resultado.reached_goal = True
            meta_handle.succeed()
            self.get_logger().info(f'🖐  pinza -> {posicion:.0f} (vel {self.velocidad})')
        else:
            resultado.position = 0.0
            resultado.effort = 0.0
            # 'stalled' NO se marca: un fallo de comando no es "pinza obstruida". Si se marcara,
            # gripper.py lo leería como éxito (reached_goal or stalled) y el orquestador creería
            # que la pinza trabajó cuando en realidad no se movió.
            resultado.stalled = False
            resultado.reached_goal = False
            self.get_logger().error(
                f'no pude comandar la pinza a {posicion:.0f} · revisa el puerto con '
                f'`fuser -v {self.puerto}` (¿lo tiene el driver sync_plan_nx?)')
            meta_handle.abort()
        return resultado


def main(args=None):
    rclpy.init(args=args)
    nodo = ServidorPinza()
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
