""" Nodo de percepción por color de la cámara montada en el brazo — Ítem 2 (Pregunta 2) """

""" El driver de la cámara publica sensor_msgs/Image (por defecto en /image_raw). Este nodo lo
suscribe, pasa el fotograma a OpenCV con cv_bridge y mira el color de CADA estación (los
rectángulos de estaciones.py). Con eso arma un MAPA {estación → color}, que es lo que permite
"encontrar" el color pedido sin importar en qué esquina esté.

La cámara va montada en el brazo, así que la detección solo es correcta con el brazo en
POSE_BUSQUEDA; el orquestador se encarga de colocarlo ahí antes de leer.

Publica en /objeto_detectado (std_msgs/String, JSON):
    {color, presente, estable, cx, cy, t, mapa_estaciones, detecciones}
  - color           : color dominante (la mancha más grande de la imagen).
  - presente        : hay algún color en la imagen.
  - estable         : el MAPA COMPLETO {estación → color} se repitió 'confirmaciones' fotogramas.
  - mapa_estaciones : {"1": "rojo", "2": null, ...} -> color visto en cada estación.
  - detecciones     : [{estacion, color, area, cx, cy}] (cx,cy en píxeles de la imagen).

Este nodo SOLO publica la detección: no mueve el brazo ni publica /joint_states.

Incluye un watchdog que avisa si no llega ninguna imagen en 'watchdog_s' segundos (casi siempre
un tópico mal configurado) y un log de TRANSICIÓN cada vez que el mapa estable cambia, para ver
en vivo que sí se está viendo la mesa sin llenar la consola de un print por frame. """

import json
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

try:
    import cv2 as cv
    import numpy as np
    from cv_bridge import CvBridge
    VISION_DISPONIBLE = True
except ImportError as _e:                       # en la Jetson con ROS estas libs están; la
    VISION_DISPONIBLE = False                  # guarda evita que el import tumbe el nodo
    _FALTA_VISION = repr(_e)

from arm_broker import estaciones


# Rangos HSV de cada color sobre el tapete (los del script probado con el kit). El rojo lleva dos
# franjas porque el tono 0/180 corta la rueda de color.
COLORES = {
    'rojo': [((0, 120, 70), (10, 255, 255)), ((170, 120, 70), (180, 255, 255))],
    'amarillo': [((20, 100, 100), (35, 255, 255))],
    'verde': [((40, 70, 70), (85, 255, 255))],
    'azul': [((90, 100, 70), (130, 255, 255))],
}


class PercepcionCamara(Node):

    def __init__(self):
        super().__init__('percepcion_camara')

        self.declare_parameter('topico_imagen', '/image_raw')
        self.declare_parameter('topico_salida', '/objeto_detectado')
        self.declare_parameter('area_min', 300)               # píxeles mínimos del manchón de color
        self.declare_parameter('confirmaciones', 5)           # fotogramas iguales para "estable"
        self.declare_parameter('watchdog_s', 5.0)             # avisa si no llegan imágenes
        self.declare_parameter('log_estado_periodico_s', 0.0)  # 0 = off; >0 = log cada N s

        self.area_min = float(self.get_parameter('area_min').value)
        self.confirmaciones = int(self.get_parameter('confirmaciones').value)
        self.watchdog_s = float(self.get_parameter('watchdog_s').value)
        self.log_periodico_s = float(self.get_parameter('log_estado_periodico_s').value)

        self.ultimo_mapa = None           # clave del último mapa visto (para contar la racha)
        self.racha = 0
        self.mapa_estable_previo = None
        self.n_frames = 0
        self.ultima_imagen_t = None       # None = todavía no llegó ninguna imagen
        self._watchdog_avisado = False

        self.pub = self.create_publisher(
            String, str(self.get_parameter('topico_salida').value), 10)

        if VISION_DISPONIBLE:
            self.bridge = CvBridge()
        else:
            self.bridge = None
            self.get_logger().error(
                f'falta OpenCV/cv_bridge ({_FALTA_VISION}); el nodo publicará vacío. '
                f'Instala python3-opencv y cv_bridge.')

        self.create_subscription(
            Image, str(self.get_parameter('topico_imagen').value), self._al_imagen, 10)
        self.create_timer(1.0, self._chequear_watchdog)

        self.get_logger().info('=' * 60)
        self.get_logger().info('  PERCEPCION_CAMARA LISTO (detección por 4 estaciones)')
        self.get_logger().info(f'  imagen : {self.get_parameter("topico_imagen").value}')
        self.get_logger().info(f'  salida : {self.get_parameter("topico_salida").value}')
        for est, datos in estaciones.ESTACIONES.items():
            self.get_logger().info(f'  estación {est}: roi={datos["roi"]}')
        self.get_logger().info('=' * 60)

    # 1. Watchdog
    def _chequear_watchdog(self):
        """Avisa UNA vez si nunca llegó una imagen, o cada watchdog_s si el flujo se corta."""
        ahora = time.time()
        if self.ultima_imagen_t is None:
            if not self._watchdog_avisado and self.watchdog_s > 0:
                self._watchdog_avisado = True
                topico = self.get_parameter('topico_imagen').value
                self.get_logger().error(
                    f'⚠️  no llegó NINGUNA imagen en {topico} tras {self.watchdog_s:.0f}s. '
                    f'Comprueba con: ros2 topic list · ros2 topic hz {topico} · '
                    f'ros2 topic info {topico} -v (el driver publica por defecto en /image_raw)')
            return
        if ahora - self.ultima_imagen_t > self.watchdog_s:
            self.get_logger().warn(
                f'⚠️  sin imágenes nuevas hace {ahora - self.ultima_imagen_t:.1f}s '
                f'(¿se cayó la cámara?)',
                throttle_duration_sec=self.watchdog_s)

    # 2. Detección por estación
    def _detectar(self, imagen):
        """Mira el color dentro de cada estación (rectángulo de estaciones.py).

        Devuelve (mapa, detalle):
          mapa   = {estación: color}  (color None si no hay cubo en esa estación)
          detalle= {estación: {color, area, cx, cy}} con cx,cy en píxeles de la imagen."""
        alto, ancho = imagen.shape[:2]
        hsv = cv.cvtColor(imagen, cv.COLOR_BGR2HSV)
        kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (5, 5))

        mapa = {}
        detalle = {}

        for est, datos in estaciones.ESTACIONES.items():
            x1, y1, x2, y2 = estaciones.escalar_roi(datos['roi'], ancho, alto)
            x1 = max(0, min(ancho - 1, x1))
            y1 = max(0, min(alto - 1, y1))
            x2 = max(0, min(ancho, x2))
            y2 = max(0, min(alto, y2))
            recorte = hsv[y1:y2, x1:x2]

            color, area, centro = None, self.area_min, None
            if recorte.size:
                for nombre, franjas in COLORES.items():
                    mascara = None
                    for bajo, tope in franjas:
                        m = cv.inRange(recorte, np.array(bajo), np.array(tope))
                        mascara = m if mascara is None else cv.bitwise_or(mascara, m)
                    mascara = cv.morphologyEx(mascara, cv.MORPH_OPEN, kernel)
                    contornos, _ = cv.findContours(mascara, cv.RETR_EXTERNAL,
                                                   cv.CHAIN_APPROX_SIMPLE)
                    if not contornos:
                        continue
                    c = max(contornos, key=cv.contourArea)
                    a = cv.contourArea(c)
                    if a > area:
                        mo = cv.moments(c)
                        if mo['m00'] != 0:
                            area = a
                            color = nombre
                            centro = (int(mo['m10'] / mo['m00']), int(mo['m01'] / mo['m00']))

            mapa[est] = color
            detalle[est] = {
                'color': color,
                'area': int(area) if color else 0,
                'cx': (x1 + centro[0]) if centro else 0,
                'cy': (y1 + centro[1]) if centro else 0,
            }

        return mapa, detalle

    # 3. Callback de imagen
    def _al_imagen(self, msg):
        # Marcar la llegada de ESTA imagen de inmediato: así el watchdog calla aunque la
        # conversión o la detección fallen más abajo.
        self.ultima_imagen_t = time.time()
        self.n_frames += 1
        if self.n_frames == 1:
            self.get_logger().info(
                f'📷 primera imagen en {self.get_parameter("topico_imagen").value} '
                f'({msg.width}x{msg.height}, encoding={msg.encoding})')

        if self.bridge is None:
            self._publicar({}, {}, None, 0, 0, False)
            return

        try:
            imagen = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().warn(f'no pude convertir la imagen: {e!r}',
                                   throttle_duration_sec=2.0)
            return

        mapa, detalle = self._detectar(imagen)

        # Color dominante global (la mancha más grande), por compatibilidad con el formato viejo.
        mejor = max(detalle, key=lambda e: detalle[e]['area'], default=None)
        if mejor is not None and detalle[mejor]['color']:
            color, cx, cy = detalle[mejor]['color'], detalle[mejor]['cx'], detalle[mejor]['cy']
        else:
            color, cx, cy = None, 0, 0

        # Racha de fotogramas con el MISMO mapa {estación → color}.
        clave = tuple((e, mapa[e]) for e in sorted(mapa))
        if clave == self.ultimo_mapa:
            self.racha += 1
        else:
            self.ultimo_mapa = clave
            self.racha = 1
        estable = self.racha >= self.confirmaciones

        # Log de TRANSICIÓN (no por frame): se ve en la terminal cada vez que el mapa estable
        # cambia. Es lo que el orquestador está esperando.
        if estable and clave != self.mapa_estable_previo:
            self.mapa_estable_previo = clave
            self.get_logger().info(f'🎯 mapa ESTABLE: {mapa}  ({detalle})')
        elif not estable and self.mapa_estable_previo is not None and self.racha == 1:
            self.get_logger().info(f'… mapa inestable: {mapa}')
            self.mapa_estable_previo = None

        if self.log_periodico_s > 0:
            self.get_logger().info(
                f'estado: mapa={mapa} estable={estable}',
                throttle_duration_sec=self.log_periodico_s)

        self._publicar(mapa, detalle, color, cx, cy, estable)

    def _publicar(self, mapa, detalle, color, cx, cy, estable):
        salida = String()
        salida.data = json.dumps({
            'color': color,
            'presente': color is not None,
            'estable': bool(estable),
            'cx': int(cx),
            'cy': int(cy),
            't': time.time(),
            'mapa_estaciones': {str(e): mapa[e] for e in mapa},
            'detecciones': [dict(estacion=e, **detalle[e]) for e in detalle],
        })
        self.pub.publish(salida)


def main(args=None):
    rclpy.init(args=args)
    nodo = PercepcionCamara()
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
