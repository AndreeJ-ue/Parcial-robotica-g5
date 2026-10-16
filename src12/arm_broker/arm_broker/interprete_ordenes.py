""" Nodo interprete_ordenes: traduce una frase en una decisión tipada — Pregunta 1 del Parcial """
""" Expone el servicio /interpretar_orden. Internamente consulta a LAYA (fuera de ROS 2,
por HTTP); si no contesta dentro de timeout_laya_s, resuelve con un clasificador local
por palabras clave y marca la respuesta como degradada. El servicio nunca se queda esperando """

import os
import time

import rclpy
from rclpy.node import Node

from arm_broker_interfaces.srv import InterpretarOrden

from arm_broker import cliente_laya
from arm_broker import clasificador_palabras_clave as clasificador
from arm_broker import decisiones


# 1. Nodo
class InterpreteOrdenes(Node):

    def __init__(self):
        super().__init__('interprete_ordenes')

        # Parámetros de ROS 2: se pasan con --ros-args -p nombre:=valor
        self.declare_parameter('laya_url', 'http://127.0.0.1:8000')   # IP:puerto predeterminado q es el local
        self.declare_parameter('timeout_laya_s', 2.0)                 # límite de espera a LAYA por defecto
        self.declare_parameter('objetos', ['cubo', 'cilindro', 'esfera'])
        self.declare_parameter('colores', ['rojo', 'verde', 'azul', 'amarillo'])
        self.declare_parameter('acciones', ['agarrar', 'soltar', 'mover', 'detener'])

        self.laya_url = str(self.get_parameter('laya_url').value).rstrip('/')
        self.timeout_laya = float(self.get_parameter('timeout_laya_s').value)
        self.objetos = list(self.get_parameter('objetos').value)
        self.colores = list(self.get_parameter('colores').value)
        self.acciones = list(self.get_parameter('acciones').value)

        # La clave de LAYA (si el servidor del laboratorio la exige) se lee de una variable
        # de entorno — NUNCA va escrita en este archivo ni se sube al repositorio
        self.laya_api_key = os.environ.get('LAYA_API_KEY', '')

        # Línea base de red: se mide una sola vez al arrancar, golpeando /health (que no hace
        # cómputo real) para poder separar después "red" de "cómputo" en cada medición
        self.get_logger().info(f'[interprete_ordenes] midiendo línea base de red hacia {self.laya_url} ...')
        try:
            self.tiempo_red_base = cliente_laya.medir_red_base(self.laya_url, self.laya_api_key)
            self.get_logger().info(
                f'[interprete_ordenes] línea base de red ≈ {self.tiempo_red_base * 1000:.0f} ms')
        except Exception as e:
            self.tiempo_red_base = 0.0
            self.get_logger().warn(
                f'[interprete_ordenes] no se pudo medir la línea base de red (¿LAYA está arriba?): {e!r}')

        self.srv = self.create_service(InterpretarOrden, 'interpretar_orden', self.callback)

        self.get_logger().info('=' * 60)
        self.get_logger().info('  INTERPRETE_ORDENES LISTO')
        self.get_logger().info(f'  servicio      : /interpretar_orden')
        self.get_logger().info(f'  LAYA           : {self.laya_url}')
        self.get_logger().info(f'  timeout_laya_s : {self.timeout_laya}')
        self.get_logger().info('=' * 60)

    # 2. Atención del servicio
    def callback(self, request, response):
        """Resuelve una frase: intenta LAYA primero (salvo forzar_clasificador=True), y si no
        responde a tiempo, contesta algo ilegible o no reconoce la acción, cae al clasificador
        local. Nunca deja al cliente esperando más de timeout_laya_s más el tiempo (rápido) del
        clasificador"""
        frase = request.frase.strip()
        t0 = time.time()

        if not frase:
            self._llenar(response, accion='desconocido', objeto='desconocido', color='ninguno',
                          prioridad=0, permitido=False, motivo='frase vacía',
                          degradada=True, fuente='palabras_clave', t0=t0)
            self.get_logger().warn('[interprete_ordenes] frase vacía recibida')
            return response

        if not request.forzar_clasificador:
            try:
                decision, _crudo = cliente_laya.preguntar(
                    self.laya_url, self.laya_api_key, frase, self.timeout_laya,
                    self.objetos, self.colores, self.acciones)

                # Solo se acepta la respuesta de LAYA si reconoció la acción: si devolvió
                # 'desconocido' (o algo que no está en la lista), se trata como respuesta
                # inválida y se resuelve con el clasificador local — nunca se completa una
                # acción a medias ni se ejecuta lo que no se entiende
                if not decisiones.accion_reconocida(decision):
                    raise ValueError(
                        f'LAYA no reconoció la acción ({decision.get("accion")!r})')

                # Red de seguridad: aunque LAYA diga permitido=True, una palabra prohibida en la
                # frase deja la orden como no permitida
                decisiones.aplicar_reglas(decision, frase)

                tiempo_total = time.time() - t0
                tiempo_red = min(self.tiempo_red_base, tiempo_total)
                tiempo_computo = max(0.0, tiempo_total - tiempo_red)

                self._llenar(response, **decision, degradada=False, fuente='laya',
                             t_total=tiempo_total, t_red=tiempo_red, t_computo=tiempo_computo)

                self.get_logger().info(
                    f'✅ [LAYA] "{frase}" → {response.accion}/{response.objeto}/{response.color} '
                    f'p={response.prioridad} permitido={response.permitido} '
                    f'· {tiempo_total * 1000:.0f} ms')
                return response

            except Exception as e:
                self.get_logger().warn(
                    f'⚠️  LAYA no respondió bien ({e!r}); '
                    f'uso el clasificador por palabras clave para "{frase}"')

        # Camino de respaldo: clasificador local (o fue pedido explícitamente). Se le aplican
        # las mismas reglas de coherencia por si acaso
        decision = decisiones.aplicar_reglas(clasificador.clasificar(frase), frase)
        tiempo_total = time.time() - t0
        self._llenar(response, **decision, degradada=True, fuente='palabras_clave',
                     t_total=tiempo_total, t_red=0.0, t_computo=0.0)

        marca = '🔁 [CLASIFICADOR, pedido]' if request.forzar_clasificador else '⚠️  [DEGRADADA]'
        self.get_logger().info(
            f'{marca} "{frase}" → {response.accion}/{response.objeto}/{response.color} '
            f'p={response.prioridad} permitido={response.permitido} '
            f'· {tiempo_total * 1000:.0f} ms')
        return response

    @staticmethod
    def _llenar(response, accion, objeto, color, prioridad, permitido, motivo,
                degradada, fuente, t0=None, t_total=None, t_red=0.0, t_computo=0.0):
        """Vuelca una decisión (dict de cliente_laya o de clasificador) en el Response del srv"""
        response.accion = accion
        response.objeto = objeto
        response.color = color
        response.prioridad = int(prioridad)
        response.permitido = bool(permitido)
        response.motivo = motivo
        response.degradada = bool(degradada)
        response.fuente = fuente
        response.tiempo_total_s = float(t_total if t_total is not None else (time.time() - t0))
        response.tiempo_red_s = float(t_red)
        response.tiempo_computo_s = float(t_computo)


# 3. Punto de entrada
def main(args=None):
    rclpy.init(args=args)
    nodo = InterpreteOrdenes()
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
