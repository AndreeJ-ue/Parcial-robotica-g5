# Configuración de rutas y namespace para las preguntas 1 y 3.
""" Nodo interprete_ordenes: convierte una frase en una decisión tipada — Ítem 1 (Pregunta 1) """

""" Expone el servicio /interpretar_orden. Por dentro consulta a LAYA (por HTTP, fuera de ROS 2)
y, si no contesta dentro de timeout_laya_s, resuelve con el clasificador local por palabras clave
y marca la respuesta como degradada. El tiempo HTTP se configura mediante timeout_laya_s. """

import os
import time

import rclpy
from rclpy.node import Node

from jetcobot_p13_interfaces.srv import InterpretarOrden

from jetcobot_p13 import cliente_laya
from jetcobot_p13 import clasificador_palabras_clave as clasificador


class NodoInterprete(Node):

    def __init__(self):
        super().__init__('interprete_ordenes', namespace='p13')

        # Parámetros de ROS 2: se pasan con --ros-args -p nombre:=valor
        self.declare_parameter('laya_url', 'http://127.0.0.1:8000')   # IP:puerto por defecto (local)
        self.declare_parameter('timeout_laya_s', 2.0)                 # espera máxima a LAYA por defecto
        self.declare_parameter('objetos', ['cubo', 'cilindro', 'esfera'])
        self.declare_parameter('colores', ['rojo', 'verde', 'azul', 'amarillo'])
        self.declare_parameter('acciones', ['agarrar', 'soltar', 'mover', 'detener'])

        self.endpoint_laya = str(self.get_parameter('laya_url').value).rstrip('/')
        self.limite_laya = float(self.get_parameter('timeout_laya_s').value)
        self.catalogo_objetos = list(self.get_parameter('objetos').value)
        self.catalogo_colores = list(self.get_parameter('colores').value)
        self.catalogo_acciones = list(self.get_parameter('acciones').value)

        # La clave de LAYA (si el servidor del laboratorio la exige) sale de una variable de
        # entorno; NUNCA va escrita en este archivo ni se sube al repositorio.
        self.clave_laya = os.environ.get('LAYA_API_KEY', '')

        # Línea base de red: se mide una sola vez al arrancar contra /health (que no hace cómputo
        # real) para poder separar después "red" de "cómputo" en cada medición.
        self.get_logger().info(
            f'[interprete_ordenes] midiendo línea base de red hacia {self.endpoint_laya} ...')
        try:
            self.red_base = cliente_laya.medir_red_base(self.endpoint_laya, self.clave_laya)
            self.get_logger().info(
                f'[interprete_ordenes] línea base de red ≈ {self.red_base * 1000:.0f} ms')
        except Exception as e:
            self.red_base = 0.0
            self.get_logger().warn(
                f'[interprete_ordenes] no se pudo medir la línea base de red '
                f'(¿LAYA está arriba?): {e!r}')

        self.servicio = self.create_service(
            InterpretarOrden, 'interpretar_orden', self.atender)

        self.get_logger().info('=' * 60)
        self.get_logger().info('  INTERPRETE_ORDENES LISTO')
        self.get_logger().info('  servicio      : /interpretar_orden')
        self.get_logger().info(f'  LAYA           : {self.endpoint_laya}')
        self.get_logger().info(f'  timeout_laya_s : {self.limite_laya}')
        self.get_logger().info('=' * 60)

    def atender(self, solicitud, respuesta):
        """Resuelve una frase: primero intenta LAYA (salvo forzar_clasificador=True) y, cuando no
        hay respuesta a tiempo, cae al clasificador local. El timeout HTTP usa la semántica de conexión/lectura de requests."""
        frase = solicitud.frase.strip()
        t0 = time.time()

        if not frase:
            self._volcar(respuesta, accion='desconocido', objeto='desconocido', color='ninguno',
                         prioridad=0, permitido=False, motivo='frase vacía',
                         degradada=True, fuente='palabras_clave', t0=t0)
            self.get_logger().warn('[interprete_ordenes] frase vacía recibida')
            return respuesta

        if not solicitud.forzar_clasificador:
            try:
                decision, _crudo = cliente_laya.preguntar(
                    self.endpoint_laya, self.clave_laya, frase, self.limite_laya,
                    self.catalogo_objetos, self.catalogo_colores, self.catalogo_acciones)

                t_total = time.time() - t0
                t_red = min(self.red_base, t_total)
                t_computo = max(0.0, t_total - t_red)

                self._volcar(respuesta, **decision, degradada=False, fuente='laya',
                             t_total=t_total, t_red=t_red, t_computo=t_computo)

                self.get_logger().info(
                    f'✅ [LAYA] "{frase}" → {respuesta.accion}/{respuesta.objeto}/{respuesta.color} '
                    f'p={respuesta.prioridad} permitido={respuesta.permitido} '
                    f'· {t_total * 1000:.0f} ms')
                return respuesta

            except Exception as e:
                self.get_logger().warn(
                    f'⚠️  LAYA no respondió a tiempo o falló ({e!r}); '
                    f'uso el clasificador por palabras clave para "{frase}"')

        # Camino de respaldo: clasificador local (o fue pedido explícitamente)
        decision = clasificador.clasificar(frase)
        t_total = time.time() - t0
        self._volcar(respuesta, **decision, degradada=True, fuente='palabras_clave',
                     t_total=t_total, t_red=0.0, t_computo=0.0)

        etiqueta = '🔁 [CLASIFICADOR, pedido]' if solicitud.forzar_clasificador else '⚠️  [DEGRADADA]'
        self.get_logger().info(
            f'{etiqueta} "{frase}" → {respuesta.accion}/{respuesta.objeto}/{respuesta.color} '
            f'p={respuesta.prioridad} permitido={respuesta.permitido} '
            f'· {t_total * 1000:.0f} ms')
        return respuesta

    @staticmethod
    def _volcar(respuesta, accion, objeto, color, prioridad, permitido, motivo,
                degradada, fuente, t0=None, t_total=None, t_red=0.0, t_computo=0.0):
        """Vuelca una decisión (dict de cliente_laya o del clasificador) en el Response del srv."""
        respuesta.accion = accion
        respuesta.objeto = objeto
        respuesta.color = color
        respuesta.prioridad = int(prioridad)
        respuesta.permitido = bool(permitido)
        respuesta.motivo = motivo
        respuesta.degradada = bool(degradada)
        respuesta.fuente = fuente
        respuesta.tiempo_total_s = float(t_total if t_total is not None else (time.time() - t0))
        respuesta.tiempo_red_s = float(t_red)
        respuesta.tiempo_computo_s = float(t_computo)


def main(args=None):
    rclpy.init(args=args)
    nodo = NodoInterprete()
    try:
        rclpy.spin(nodo)
    except KeyboardInterrupt:
        pass
    finally:
        nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
