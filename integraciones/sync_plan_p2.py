"""Adaptación de sync_plan_nx: un puerto, comandos radianes, medidas y pinza.

Al iniciar solo lee. Habilitar comandos después de preparar el broker/escena.
No ejecutar junto a otro driver o notebook que tenga abierto el mismo puerto.
"""
import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from sensor_msgs.msg import JointState
from pymycobot.mycobot import MyCobot
from arm_broker_interfaces.srv import AccionarPinza

NOMBRES = ['1_Joint','2_Joint','3_Joint','4_Joint','5_Joint','6_Joint']


def ordenar_radianes(msg):
    if len(msg.name) != len(msg.position) or len(set(msg.name)) != len(msg.name):
        raise ValueError('Nombres y posiciones articulares inconsistentes')
    por_nombre = dict(zip(msg.name, msg.position))
    q = [float(por_nombre[n]) for n in NOMBRES]
    if not all(math.isfinite(v) for v in q):
        raise ValueError('Posiciones no finitas')
    # Los límites del broker siguen siendo la admisión principal.
    if any(abs(v) > math.pi for v in q):
        raise ValueError('Comando fuera de radianes/rango esperado')
    return q


class DriverP2(Node):
    def __init__(self):
        super().__init__('driver_p2')
        for nombre, valor in {'port':'/dev/ttyUSB0','baud':1000000,
                              'min_period_s':0.05,'min_delta_deg':0.5,'speed':20,
                              'hz_medicion':5.0,'speed_pinza':30,
                              'pinza_abierta':100,'pinza_cerrada':0,
                              'habilitar_comandos':False}.items():
            self.declare_parameter(nombre, valor)
        self.serial_lock = threading.RLock()
        self.last_send_time = 0.0
        self.last_sent = None
        self.modo_preparado = False
        hz = float(self.get_parameter('hz_medicion').value)
        if not math.isfinite(hz) or not 0 < hz <= 20:
            raise ValueError('hz_medicion debe estar entre 0 y 20')
        self.mc = MyCobot(self.get_parameter('port').value,
                         self.get_parameter('baud').value)
        # No hay home, reset, apertura de pinza ni send_angles al iniciar.
        self.pub_medida = self.create_publisher(JointState, '/arm/joint_states_measured', 10)
        self.grupo_control=MutuallyExclusiveCallbackGroup()
        self.grupo_medidas=MutuallyExclusiveCallbackGroup()
        self.subscription = self.create_subscription(JointState, '/joint_states', self.listener_callback, 10,callback_group=self.grupo_control)
        self.timer = self.create_timer(1/hz, self.medir,callback_group=self.grupo_medidas)
        self.servicio = self.create_service(AccionarPinza, '/arm/accionar_pinza', self.pinza,callback_group=self.grupo_control)
        self.get_logger().info('Driver P2 listo: lectura de ángulos activa; comandos deshabilitados por defecto.')

    def listener_callback(self, msg):
        if not self.get_parameter('habilitar_comandos').value:
            return
        try:
            q = ordenar_radianes(msg)
            grados = [round(math.degrees(v), 3) for v in q]
            now = time.monotonic()
            periodo = float(self.get_parameter('min_period_s').value)
            delta = float(self.get_parameter('min_delta_deg').value)
            velocidad = int(self.get_parameter('speed').value)
            if not math.isfinite(periodo) or periodo < 0 or not math.isfinite(delta) or delta < 0 or not 1 <= velocidad <= 100:
                raise ValueError('Configuración de velocidad/filtro inválida')
            if now-self.last_send_time < periodo:
                return
            if self.last_sent is not None and max(abs(a-b) for a,b in zip(grados,self.last_sent)) < delta:
                return
            with self.serial_lock:
                if not self.modo_preparado:
                    modo = self.mc.get_fresh_mode()
                    if modo == 0:
                        self.mc.set_fresh_mode(1)
                    elif modo != 1:
                        raise RuntimeError('No se pudo leer el modo de recepción del brazo')
                    self.modo_preparado = True
                self.mc.send_angles(grados, velocidad)
            self.last_send_time, self.last_sent = now, grados
        except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
            self.get_logger().error('Comando rechazado por el driver: '+str(exc))

    def medir(self):
        try:
            with self.serial_lock:
                grados = self.mc.get_angles()
            if not isinstance(grados,(list,tuple)) or len(grados) != 6:
                return
            q = [math.radians(float(v)) for v in grados]
            if not all(math.isfinite(v) for v in q):
                return
            msg = JointState()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.name, msg.position = list(NOMBRES), q
            self.pub_medida.publish(msg)
        except (TypeError, ValueError, OSError, RuntimeError) as exc:
            self.get_logger().warn('Lectura articular no disponible: '+str(exc))

    def pinza(self, req, res):
        res.completado = False
        if not self.get_parameter('habilitar_comandos').value:
            res.motivo = 'Comandos deshabilitados en el driver'
            return res
        if not math.isfinite(req.timeout_s) or not 0 < req.timeout_s <= 15:
            res.motivo = 'Tiempo límite de pinza inválido'
            return res
        try:
            objetivo = int(self.get_parameter('pinza_abierta' if req.abrir else 'pinza_cerrada').value)
            velocidad = int(self.get_parameter('speed_pinza').value)
            if not 0 <= objetivo <= 100 or not 1 <= velocidad <= 100:
                raise ValueError('Configuración de pinza inválida')
            limite = time.monotonic()+req.timeout_s
            with self.serial_lock:self.mc.set_gripper_value(objetivo, velocidad)
            time.sleep(min(.2,req.timeout_s))
            while time.monotonic() < limite:
                with self.serial_lock:
                    estado = self.mc.is_gripper_moving()
                    if estado == 0:
                        valor = self.mc.get_gripper_value()
                        if not isinstance(valor,(int,float)) or not math.isfinite(valor) or not 0 <= valor <= 100:
                            raise RuntimeError('Lectura de pinza inválida')
                        if req.abrir and abs(valor-objetivo)>10:
                            raise RuntimeError('Pinza no confirmó apertura')
                        # Un objeto puede impedir llegar al cero al cerrar.
                        # Motor detenido no certifica un objeto agarrado.
                        res.completado = True
                        res.motivo = 'Pinza detenida; éxito físico del agarre requiere observar objeto y zona'
                        return res
                    if estado != 1:
                        raise RuntimeError('La pinza no informa estado de movimiento válido')
                time.sleep(.05)
            raise TimeoutError('La pinza no confirmó fin dentro del plazo')
        except (OSError, ValueError, RuntimeError, TypeError, AttributeError) as exc:
            res.motivo = str(exc)
        return res

    def cerrar_puerto(self):
        with self.serial_lock:
            self.mc.close()


def main():
    rclpy.init()
    nodo = None
    executor=MultiThreadedExecutor(num_threads=2)
    try:
        nodo = DriverP2()
        executor.add_node(nodo);executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        if nodo is not None:
            try:
                nodo.cerrar_puerto()
            finally:
                nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
