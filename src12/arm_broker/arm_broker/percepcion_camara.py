""" Nodo de percepción por color de la cámara — Pregunta 2 """

""" usb_cam publica sensor_msgs/Image en el tópico de imagen (por defecto /image_raw). Este nodo
lo suscribe, convierte el fotograma con cv_bridge a OpenCV y detecta el color de CADA UNA de las
4 posiciones (las ROIs de zonas.py). Con eso arma un MAPA {slot: color} que es lo que permite
"encontrar" el color pedido, sin importar en qué esquina esté.

Salida: /objeto_detectado (std_msgs/String, JSON) con
    {color, presente, estable, cx, cy, t, por_slot, detecciones}
donde:
    - 'color'      : color dominante (la mancha más grande de la imagen), por compatibilidad.
    - 'presente'   : hay algún color.
    - 'estable'    : el MAPA COMPLETO {slot: color} se repitió 'confirmaciones' fotogramas.
    - 'por_slot'   : {"1": "rojo", "2": null, ...} -> el color visto en cada posición.
    - 'detecciones': lista con {slot, color, area, cx, cy} (cx,cy en coordenadas de la imagen).

Este nodo SOLO publica la detección: no mueve el brazo.

Trae dos avisos útiles:
  - un watchdog que avisa si no llega ninguna imagen en 'watchdog_s' segundos (típico cuando
    'topico_imagen' no coincide con lo que usb_cam realmente publica), y
  - un log (no un print por frame) cada vez que el mapa estable cambia, para ver en vivo que
    sí está viendo la mesa sin inundar la consola. """

import json
import time

import cv2 as cv
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

try:
    from arm_broker import zonas
except ImportError:                      # por si se ejecuta suelto desde la carpeta del paquete
    import zonas


# Rangos HSV de cada color sobre la mesa (los del script probado con el kit)
COLORES_HSV = {
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
        self.declare_parameter('area_min', 300)          # píxeles mínimos del manchón de color
        self.declare_parameter('confirmaciones', 5)      # fotogramas iguales para marcar "estable"
        self.declare_parameter('watchdog_s', 5.0)        # avisa si no llegan imágenes en este tiempo
        self.declare_parameter('log_estado_periodico_s', 0.0)  # 0 = desactivado; >0 = log cada N s

        self.area_min = float(self.get_parameter('area_min').value)
        self.confirmaciones = int(self.get_parameter('confirmaciones').value)
        self.watchdog_s = float(self.get_parameter('watchdog_s').value)
        self.log_periodico_s = float(self.get_parameter('log_estado_periodico_s').value)

        self.bridge = CvBridge()
        self.ultimo_mapa = None            # clave del último mapa visto (para contar la racha)
        self.racha = 0
        self.mapa_estable_anterior = None
        self.n_frames = 0
        self.ultima_imagen_t = None       # None = todavía no llegó ninguna imagen
        self._watchdog_avisado = False
        self.pub = self.create_publisher(
            String, str(self.get_parameter('topico_salida').value), 10)
        self.create_subscription(
            Image, str(self.get_parameter('topico_imagen').value), self._on_imagen, 10)

        # Watchdog: si en 'watchdog_s' segundos no llegó ninguna imagen, es casi siempre un
        # tópico mal configurado (usb_cam publicando en otro nombre). Se revisa cada segundo.
        self.create_timer(1.0, self._chequear_watchdog)

        self.get_logger().info('=' * 60)
        self.get_logger().info('  PERCEPCION_CAMARA LISTO (deteccion por 4 zonas)')
        self.get_logger().info(f'  imagen : {self.get_parameter("topico_imagen").value}')
        self.get_logger().info(f'  salida : {self.get_parameter("topico_salida").value}')
        for slot, z in zonas.ZONAS.items():
            self.get_logger().info(f'  slot {slot}: roi={z["roi"]}')
        self.get_logger().info('=' * 60)

    def _chequear_watchdog(self):
        """Avisa UNA vez si nunca llegó una imagen, o si dejaron de llegar por watchdog_s."""
        ahora = time.time()
        if self.ultima_imagen_t is None:
            # Nunca llegó nada: probablemente el tópico no coincide con el que usb_cam publica
            if not self._watchdog_avisado and self.watchdog_s > 0:
                self._watchdog_avisado = True
                topico = self.get_parameter('topico_imagen').value
                self.get_logger().error(
                    f'⚠️  no llegó NINGUNA imagen en {topico} tras {self.watchdog_s:.0f}s. '
                    f'Verifica con: ros2 topic list | grep -i image  ·  ros2 topic hz {topico}  '
                    f'·  ros2 topic info {topico} -v. '
                    f'(usb_cam_node_exe publica por defecto en /image_raw)')
            return
        # Ya llegaron imágenes alguna vez: avisar si el flujo se cortó
        if ahora - self.ultima_imagen_t > self.watchdog_s:
            self.get_logger().warn(
                f'⚠️  sin imágenes nuevas hace {ahora - self.ultima_imagen_t:.1f}s '
                f'(¿se cayó usb_cam o la cámara?)',
                throttle_duration_sec=self.watchdog_s)

    def _detectar(self, cv_img):
        """Detecta el color dentro de cada ROI de zonas.py.

        Devuelve (por_slot, detalle):
          por_slot = {slot: color}  (color None si no hay cubo en esa posición)
          detalle  = {slot: {color, area, cx, cy}} con cx,cy en coordenadas de la imagen."""
        alto, ancho = cv_img.shape[:2]
        hsv = cv.cvtColor(cv_img, cv.COLOR_BGR2HSV)
        kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (5, 5))

        por_slot = {}
        detalle = {}

        for slot, z in zonas.ZONAS.items():
            x1, y1, x2, y2 = zonas.escalar_roi(z['roi'], ancho, alto)
            x1 = max(0, min(ancho - 1, x1))
            y1 = max(0, min(alto - 1, y1))
            x2 = max(0, min(ancho, x2))
            y2 = max(0, min(alto, y2))
            roi = hsv[y1:y2, x1:x2]

            mejor_color, mejor_area, mejor_centro = None, self.area_min, None
            if roi.size:
                for nombre, rangos in COLORES_HSV.items():
                    mascara = None
                    for bajo, alto_hsv in rangos:
                        m = cv.inRange(roi, np.array(bajo), np.array(alto_hsv))
                        mascara = m if mascara is None else cv.bitwise_or(mascara, m)
                    mascara = cv.morphologyEx(mascara, cv.MORPH_OPEN, kernel)
                    contornos, _ = cv.findContours(mascara, cv.RETR_EXTERNAL,
                                                   cv.CHAIN_APPROX_SIMPLE)
                    if not contornos:
                        continue
                    c = max(contornos, key=cv.contourArea)
                    area = cv.contourArea(c)
                    if area > mejor_area:
                        mo = cv.moments(c)
                        if mo['m00'] != 0:
                            mejor_area = area
                            mejor_color = nombre
                            mejor_centro = (int(mo['m10'] / mo['m00']),
                                            int(mo['m01'] / mo['m00']))

            por_slot[slot] = mejor_color
            detalle[slot] = {
                'color': mejor_color,
                'area': int(mejor_area) if mejor_color else 0,
                'cx': (x1 + mejor_centro[0]) if mejor_centro else 0,
                'cy': (y1 + mejor_centro[1]) if mejor_centro else 0,
            }

        return por_slot, detalle

    def _on_imagen(self, msg):
        # Se marca la llegada de ESTA imagen de inmediato: así el watchdog ya no se queja
        # aunque la conversión o la detección fallen más abajo.
        self.ultima_imagen_t = time.time()
        self.n_frames += 1
        if self.n_frames == 1:
            self.get_logger().info(
                f'📷 primera imagen recibida en {self.get_parameter("topico_imagen").value} '
                f'({msg.width}x{msg.height}, encoding={msg.encoding})')

        try:
            cv_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().warn(f'no pude convertir la imagen: {e!r}', throttle_duration_sec=2.0)
            return

        por_slot, detalle = self._detectar(cv_img)

        # Color dominante global (la mancha más grande), por compatibilidad con el formato viejo.
        mejor_slot = max(detalle, key=lambda s: detalle[s]['area'], default=None)
        if mejor_slot is not None and detalle[mejor_slot]['color']:
            color = detalle[mejor_slot]['color']
            cx, cy = detalle[mejor_slot]['cx'], detalle[mejor_slot]['cy']
        else:
            color, cx, cy = None, 0, 0

        # Se cuenta la racha de fotogramas con el MISMO MAPA completo {slot: color}.
        mapa_key = tuple((s, por_slot[s]) for s in sorted(por_slot))
        if mapa_key == self.ultimo_mapa:
            self.racha += 1
        else:
            self.ultimo_mapa = mapa_key
            self.racha = 1

        estable = self.racha >= self.confirmaciones

        # Log de TRANSICIÓN (no de cada frame): se ve en la terminal cada vez que el mapa
        # estable cambia. Es lo que orquestador_item2 está esperando.
        if estable and mapa_key != self.mapa_estable_anterior:
            self.mapa_estable_anterior = mapa_key
            self.get_logger().info(f'🎯 mapa ESTABLE: {por_slot}  ({detalle})')
        elif not estable and self.mapa_estable_anterior is not None and self.racha == 1:
            self.get_logger().info(f'… mapa inestable: {por_slot}')
            self.mapa_estable_anterior = None

        # Log periódico opcional (apagado por defecto): útil para ver que el nodo sigue vivo.
        if self.log_periodico_s > 0:
            self.get_logger().info(
                f'estado: por_slot={por_slot} estable={estable}',
                throttle_duration_sec=self.log_periodico_s)

        salida = String()
        salida.data = json.dumps({
            'color': color,
            'presente': color is not None,
            'estable': bool(estable),
            'cx': int(cx),
            'cy': int(cy),
            't': time.time(),
            'por_slot': {str(s): por_slot[s] for s in por_slot},
            'detecciones': [dict(slot=s, **detalle[s]) for s in detalle],
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
