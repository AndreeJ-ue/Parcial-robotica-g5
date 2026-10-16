#!/usr/bin/env python3
""" Verificador de la visión por estaciones del Ítem 2 — cámara montada en el brazo.

Para qué sirve: la cámara va montada EN EL BRAZO, así que solo ve bien el tapete con el brazo en
POSE_BUSQUEDA. Con el brazo en esa pose, este script abre la cámara a 640x480, dibuja los cuatro
rectángulos de estación (estaciones.py) y marca el color que se ve en cada uno. Es la forma de
comprobar en vivo que las ROIs caen sobre las cuatro esquinas y que los rangos HSV detectan bien
cada cubo. El número de estación (1..4) es el contrato entre visión y movimiento:

    1 = arriba-izquierda      2 = arriba-derecha
    3 = abajo-izquierda       4 = abajo-derecha

Los rectángulos NO se calibraron a mano: son los cuadrantes naturales de la imagen 640x480, así
que no hay nada que "hacer clic". Si movieran la cámara (p. ej. cambiar POSE_BUSQUEDA), no hay que
recalibrar píxeles; solo revisar que los cubos caigan dentro de su cuadrante.

Uso (solo cámara; el brazo ya está en POSE_BUSQUEDA):
    python3 herramientas/calibrar_camara.py --guardar foto_estaciones.jpg

Uso (manda el brazo al broker hasta POSE_BUSQUEDA y luego abre la cámara):
    python3 herramientas/calibrar_camara.py --mover-brazo --guardar foto_estaciones.jpg

SIN pantalla (SSH, terminal de Jupyter, error "could not initialize GTK backend"): usa
    python3 herramientas/calibrar_camara.py --headless --mover-brazo
que NO abre ventana: guarda la foto anotada y sale.
"""

import argparse
import sys
import time

ANCHO_FRAME = 640
ALTO_FRAME = 480


def mover_brazo_a_busqueda(paso_rad=1.5, timeout_s=60.0):
    """Manda al BROKER los goals move_arm necesarios para llegar a POSE_BUSQUEDA.

    Respeta la regla dura: solo LEE /joint_states (nunca publica) y envía goals a la acción
    move_arm. Requiere el broker corriendo y el paquete arm_broker instalado y activado.
    """
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from sensor_msgs.msg import JointState
    from arm_broker_interfaces.action import MoveArm
    from arm_broker import poses

    class _CalibradorBrazo(Node):
        def __init__(self):
            super().__init__('calibrador_camara')
            self.q_actual_rad = None
            self.create_subscription(JointState, '/joint_states', self._al_joint, 10)
            self.accion = ActionClient(self, MoveArm, 'move_arm')

        def _al_joint(self, msg):
            self.q_actual_rad = [float(v) for v in msg.position]

        def esperar_pose_actual(self, timeout_s=5.0):
            t0 = time.time()
            while self.q_actual_rad is None and time.time() - t0 < timeout_s:
                rclpy.spin_once(self, timeout_sec=0.1)
            return self.q_actual_rad

        def enviar_goal(self, q_rad):
            if not self.accion.wait_for_server(timeout_sec=10.0):
                print('[CALIBRADOR] el broker no aparece (¿está corriendo arm_broker?)')
                return False
            goal = MoveArm.Goal()
            goal.joint_positions = [float(v) for v in q_rad]
            goal.client_id = 'calibrador_camara'
            goal.priority = 200
            envio = self.accion.send_goal_async(goal)
            t0 = time.time()
            while not envio.done() and time.time() - t0 < 10.0:
                rclpy.spin_once(self, timeout_sec=0.1)
            handle = envio.result()
            if handle is None or not handle.accepted:
                print('[CALIBRADOR] el broker RECHAZÓ el goal (ver rechazos.csv del broker)')
                return False
            resultado = handle.get_result_async()
            t0 = time.time()
            while not resultado.done() and time.time() - t0 < timeout_s:
                rclpy.spin_once(self, timeout_sec=0.1)
            return resultado.done()

    rclpy.init()
    nodo = _CalibradorBrazo()
    try:
        actual = nodo.esperar_pose_actual()
        if actual is None:
            print('[CALIBRADOR] no llegó ningún /joint_states; '
                  '¿está el broker y el driver corriendo?')
            return False
        metas = poses.trozar(actual, poses.a_radianes(poses.POSE_BUSQUEDA), paso_rad)
        print(f'[CALIBRADOR] yendo a POSE_BUSQUEDA en {len(metas)} meta(s)...')
        for q_rad in metas:
            if not nodo.enviar_goal(q_rad):
                return False
        print('[CALIBRADOR] brazo en POSE_BUSQUEDA')
        return True
    finally:
        nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def abrir_camara(cv, indice):
    indices = [indice] if indice is not None else [0, 1, 2, 3]
    for i in indices:
        cap = cv.VideoCapture(i)
        if cap.isOpened():
            cap.set(cv.CAP_PROP_FRAME_WIDTH, ANCHO_FRAME)
            cap.set(cv.CAP_PROP_FRAME_HEIGHT, ALTO_FRAME)
            ok, _ = cap.read()
            if ok:
                print(f'[CALIBRADOR] cámara abierta en índice {i}')
                return cap
        cap.release()
    return None


def rangos_hsv():
    """Rangos HSV por color. Reutiliza los de percepcion_camara si están; si no, los locales."""
    try:
        from arm_broker.percepcion_camara import COLORES
        return COLORES
    except Exception:
        return {
            'rojo': [((0, 120, 70), (10, 255, 255)), ((170, 120, 70), (180, 255, 255))],
            'amarillo': [((20, 100, 100), (35, 255, 255))],
            'verde': [((40, 70, 70), (85, 255, 255))],
            'azul': [((90, 100, 70), (130, 255, 255))],
        }


def detectar_por_estacion(frame):
    """Devuelve {estación: {'color', 'area', 'cx', 'cy', 'roi'}} mirando cada rectángulo de
    estaciones.py. Nunca lanza: ante cualquier problema, {}."""
    try:
        import cv2 as cv
        import numpy as np
        from arm_broker import estaciones
    except Exception as e:
        print(f'[CALIBRADOR] falta OpenCV o el paquete arm_broker: {e!r}')
        return {}

    colores = rangos_hsv()
    alto, ancho = frame.shape[:2]
    hsv = cv.cvtColor(frame, cv.COLOR_BGR2HSV)
    kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (5, 5))

    resultado = {}
    for est, datos in estaciones.ESTACIONES.items():
        roi_px = estaciones.escalar_roi(datos['roi'], ancho, alto)
        x1, y1, x2, y2 = roi_px
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(ancho, x2), min(alto, y2)
        recorte = hsv[y1:y2, x1:x2]

        color, area, centro = None, 300.0, None
        if recorte.size:
            for nombre, franjas in colores.items():
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
        resultado[est] = {
            'color': color,
            'area': int(area) if color else 0,
            'cx': (x1 + centro[0]) if centro else 0,
            'cy': (y1 + centro[1]) if centro else 0,
            'roi': roi_px,
        }
    return resultado


def dibujar_rejilla(cv, frame, paso):
    """Superpone una rejilla de coordenadas para leer (x, y) a ojo."""
    if paso <= 0:
        return frame
    alto, ancho = frame.shape[:2]
    for x in range(0, ancho, paso):
        cv.line(frame, (x, 0), (x, alto), (128, 128, 128), 1)
        cv.putText(frame, str(x), (x + 2, 12), cv.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
    for y in range(0, alto, paso):
        cv.line(frame, (0, y), (ancho, y), (128, 128, 128), 1)
        cv.putText(frame, str(y), (2, y + 12), cv.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
    return frame


def anotar(cv, frame, deteccion):
    """Dibuja el rectángulo de cada estación y el color detectado con su centro."""
    for est, d in deteccion.items():
        x1, y1, x2, y2 = d['roi']
        cv.rectangle(frame, (x1, y1), (x2, y2), (255, 200, 0), 2)
        etiqueta = f"est{est}: {d['color'] or '-'}"
        cv.putText(frame, etiqueta, (x1 + 6, y1 + 22), cv.FONT_HERSHEY_SIMPLEX,
                   0.6, (255, 255, 255), 2)
        if d['color']:
            cv.circle(frame, (d['cx'], d['cy']), 8, (255, 255, 255), 2)
    return frame


def imprimir_deteccion(deteccion):
    print('[CALIBRADOR] color por estación:')
    for est in sorted(deteccion):
        d = deteccion[est]
        print(f"    est{est} roi={d['roi']} color={d['color'] or '(nada)'} "
              f"area={d['area']} centro=({d['cx']}, {d['cy']})")


def capturar_anotada(cv, cap, paso, espera, guardar):
    """Toma un frame asentado (headless), lo anota con ROIs + colores y lo guarda."""
    print(f'[CALIBRADOR] esperando {espera:.1f}s a que se asiente la imagen...')
    time.sleep(espera)
    frame = None
    for _ in range(10):
        ok, leido = cap.read()
        if ok:
            frame = leido
        time.sleep(0.05)
    if frame is None:
        print('[CALIBRADOR] no se pudo leer ningún frame de la cámara')
        return

    anotar(cv, frame, detectar_por_estacion(frame))
    dibujar_rejilla(cv, frame, paso)
    cv.imwrite(guardar, frame)
    print(f'[CALIBRADOR] foto guardada en: {guardar}')
    imprimir_deteccion(detectar_por_estacion(frame))


def main():
    ap = argparse.ArgumentParser(description='Verifica la visión por estaciones (ROIs).')
    ap.add_argument('--indice', type=int, default=None,
                    help='índice de la cámara (por defecto: autodetecta 0..3)')
    ap.add_argument('--guardar', metavar='RUTA', default=None,
                    help='guarda el frame anotado en esta ruta (p. ej. foto_estaciones.jpg)')
    ap.add_argument('--mover-brazo', action='store_true',
                    help='manda un goal move_arm hasta POSE_BUSQUEDA antes de abrir la cámara')
    ap.add_argument('--paso', type=float, default=1.5,
                    help='paso de troceado en radianes para ir a POSE_BUSQUEDA (default 1.5)')
    ap.add_argument('--headless', action='store_true',
                    help='sin ventana: guarda una foto anotada y sale')
    ap.add_argument('--espera', type=float, default=2.0,
                    help='segundos de asentado antes de capturar en --headless (default 2.0)')
    ap.add_argument('--rejilla', type=int, default=40,
                    help='paso de la rejilla de coordenadas en px para --headless (default 40)')
    args = ap.parse_args()

    try:
        import cv2 as cv
    except ImportError:
        sys.exit('FALLO: falta OpenCV. Instala python3-opencv (Jetson) o pip install opencv-python.')

    print('=' * 64)
    print('  VERIFICADOR DE VISIÓN POR ESTACIONES (Ítem 2)')
    print('  estaciones: 1=arriba-izq  2=arriba-der  3=abajo-izq  4=abajo-der')
    if args.headless:
        print('  MODO HEADLESS: sin ventana; guarda una foto anotada y sale')
    else:
        print('  q o ESC para salir')
    print('=' * 64)

    if args.mover_brazo:
        if not mover_brazo_a_busqueda(paso_rad=args.paso):
            print('[CALIBRADOR] continúo SIN mover el brazo (ponlo a mano en POSE_BUSQUEDA)')

    cap = abrir_camara(cv, args.indice)
    if cap is None:
        sys.exit('FALLO: no se encontró cámara disponible.')

    if args.headless:
        try:
            capturar_anotada(cv, cap, args.rejilla, args.espera,
                             args.guardar or 'foto_estaciones.jpg')
        finally:
            cap.release()
        return

    ventana = 'calibrar_camara - vision por estaciones'
    cv.namedWindow(ventana)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            anotar(cv, frame, detectar_por_estacion(frame))
            cv.putText(frame, 'q/ESC: salir', (10, 25), cv.FONT_HERSHEY_SIMPLEX,
                       0.7, (0, 255, 0), 2)
            cv.imshow(ventana, frame)
            tecla = cv.waitKey(1) & 0xFF
            if tecla in (ord('q'), 27):
                break
            if tecla == ord('s') and args.guardar:
                cv.imwrite(args.guardar, frame)
                print(f'  foto guardada en {args.guardar}')
    finally:
        cap.release()
        cv.destroyAllWindows()


if __name__ == '__main__':
    main()
