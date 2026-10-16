""" Cliente de texto: frase por teclado → /interpretar_orden → /orden_decidida — Pregunta 2 """

""" Permite que cada uno de los 4 integrantes envíe órdenes en paralelo SIN voz (útil para la
Pregunta 2). Hace exactamente lo mismo que transcriptor_voz en modo teclado: obtiene la decisión
tipada del servicio de la Pregunta 1 y la publica para que el orquestador la consuma.

Uso (una terminal por integrante):
    ros2 run arm_broker cliente_texto --ros-args -r __node:=cliente_samuel \
      -p client_id:=samuel -p n_ordenes:=0
"""

import json
import time

import rclpy
from rclpy.node import Node

from std_msgs.msg import String

from arm_broker_interfaces.srv import InterpretarOrden


class ClienteTexto(Node):

    def __init__(self):
        super().__init__('cliente_texto')
        self.declare_parameter('client_id', 'integrante')
        self.declare_parameter('n_ordenes', 0)              # <=0 = infinito (hasta Ctrl-C)
        self.declare_parameter('topico_decision', 'orden_decidida')

        self.client_id = str(self.get_parameter('client_id').value)
        self.n_ordenes = int(self.get_parameter('n_ordenes').value)

        self.cli = self.create_client(InterpretarOrden, 'interpretar_orden')
        self.pub = self.create_publisher(
            String, str(self.get_parameter('topico_decision').value), 10)

    def _interpretar(self, frase):
        req = InterpretarOrden.Request()
        req.frase = frase
        req.forzar_clasificador = False
        futuro = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, futuro)
        return futuro.result()

    def correr(self):
        if not self.cli.wait_for_service(timeout_sec=10.0):
            self.get_logger().error('/interpretar_orden no aparece (¿corre interprete_ordenes?)')
            return
        infinito = self.n_ordenes <= 0
        i = 1
        while rclpy.ok() and (infinito or i <= self.n_ordenes):
            frase = input(f'[{self.client_id}] orden {i}: ').strip()
            if not frase:
                continue
            dec = self._interpretar(frase)
            if dec is None:
                self.get_logger().warn('sin respuesta del servicio')
                continue
            msg = String()
            msg.data = json.dumps({
                'frase': frase,
                'accion': dec.accion, 'objeto': dec.objeto, 'color': dec.color,
                'prioridad': int(dec.prioridad), 'permitido': bool(dec.permitido),
                'motivo': dec.motivo, 'fuente': dec.fuente, 'degradada': bool(dec.degradada),
                't3': time.time(), 'client_id': self.client_id,
            }, ensure_ascii=False)
            self.pub.publish(msg)
            self.get_logger().info(
                f'➡️  {dec.accion}/{dec.objeto}/{dec.color} p={dec.prioridad} '
                f'permitido={dec.permitido}')
            i += 1


def main(args=None):
    rclpy.init(args=args)
    nodo = ClienteTexto()
    try:
        nodo.correr()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
