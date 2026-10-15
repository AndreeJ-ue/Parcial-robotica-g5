""" Cliente de frases por teclado para probar el Ítem 2 sin voz — Ítem 2 """

""" Escribe una frase, llama al servicio /interpretar_orden del Ítem 1 y publica la decisión en
/orden_decidida con el MISMO formato JSON que usa transcriptor_voz, para que el orquestador la
consuma igual que una orden hablada. No publica /joint_states ni mueve el brazo por su cuenta. """

import json
import time

import rclpy
from rclpy.node import Node

from std_msgs.msg import String

from arm_broker_interfaces.srv import InterpretarOrden


class ClienteTexto(Node):

    def __init__(self):
        super().__init__('cliente_texto')

        self.declare_parameter('topico_decision', 'orden_decidida')
        self.declare_parameter('forzar_clasificador', False)

        self.forzar = bool(self.get_parameter('forzar_clasificador').value)
        self.cliente = self.create_client(InterpretarOrden, 'interpretar_orden')
        self.pub = self.create_publisher(
            String, str(self.get_parameter('topico_decision').value), 10)

    def enviar_frase(self, frase):
        if not self.cliente.wait_for_service(timeout_sec=10.0):
            self.get_logger().error('/interpretar_orden no aparece: ¿corre interprete_ordenes?')
            return
        solicitud = InterpretarOrden.Request()
        solicitud.frase = frase
        solicitud.forzar_clasificador = self.forzar
        futuro = self.cliente.call_async(solicitud)
        rclpy.spin_until_future_complete(self, futuro)
        dec = futuro.result()
        if dec is None:
            self.get_logger().error('el servicio no devolvió decisión')
            return

        msg = String()
        msg.data = json.dumps({
            'frase': frase,
            'accion': dec.accion,
            'objeto': dec.objeto,
            'color': dec.color,
            'prioridad': int(dec.prioridad),
            'permitido': bool(dec.permitido),
            'motivo': dec.motivo,
            'fuente': dec.fuente,
            'degradada': bool(dec.degradada),
            't3': time.time(),
        }, ensure_ascii=False)
        self.pub.publish(msg)
        self.get_logger().info(
            f'🧭 {dec.accion}/{dec.objeto}/{dec.color} p={dec.prioridad} '
            f'permitido={dec.permitido} → publicado en /orden_decidida')

    def correr(self):
        self.get_logger().info('Escriba una orden por línea (ENTER vacío para salir).')
        while rclpy.ok():
            try:
                frase = input('orden> ').strip()
            except EOFError:
                break
            if not frase:
                break
            self.enviar_frase(frase)


def main(args=None):
    rclpy.init(args=args)
    nodo = ClienteTexto()
    try:
        nodo.correr()
    except KeyboardInterrupt:
        pass
    finally:
        nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
