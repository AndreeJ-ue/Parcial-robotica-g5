#!/usr/bin/env python3
""" Calibrador de anclas de cámara del Ítem 2 — ver y extraer las posiciones de los cubos.

Para qué sirve: la cámara está montada EN EL BRAZO, así que solo ve bien la mesa cuando el
brazo está en POSE_BUSQUEDA. Con el brazo en esa pose, este script abre la cámara a 640x480,
muestra la imagen en vivo y deja que ustedes hagan CLIC en las cuatro esquinas de la mesa, en
orden pos1, pos2, pos3, pos4. El nombre de cada posN debe coincidir con su pose de poses.py:
    pos1 = abajo_derecha     pos2 = abajo_izquierda
    pos3 = arriba_derecha    pos4 = arriba_izquierda
(esquinas tal como se ven en la IMAGEN de la cámara; respetar este orden evita espejar las
anclas respecto a las poses). Al terminar imprime la cadena exacta para copiar en el orquestador:

    -p anclas_camara:="['pos1=<x>,<y>','pos2=<x>,<y>','pos3=<x>,<y>','pos4=<x>,<y>']"

Uso (solo cámara; el brazo ya está en POSE_BUSQUEDA):
    python3 herramientas/calibrar_camara.py --guardar foto_anclas.jpg

Uso (manda el brazo al broker hasta POSE_BUSQUEDA y luego abre la cámara):
    python3 herramientas/calibrar_camara.py --mover-brazo --guardar foto_anclas.jpg

Controles en la ventana:
    clic izquierdo : fija el cubo actual (pos1 -> pos4)
    r              : reinicia los clics
    s              : guarda una foto anotada
    q o ESC        : termina e imprime la cadena de anclas

SIN pantalla (SSH, terminal de Jupyter, error "could not initialize GTK backend"): usa
    python3 herramientas/calibrar_camara.py --headless --mover-brazo
que NO abre ventana: guarda una foto anotada (rejilla + centros de color) y sale.
"""

import argparse
import sys
import time

ANCHO_FRAME = 640
ALTO_FRAME = 480
POSICIONES_ORDEN = ['pos1', 'pos2', 'pos3', 'pos4']


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


def cadena_anclas(clics):
    partes = [f"'{nombre}={clics[nombre][0]},{clics[nombre][1]}'"
              for nombre in POSICIONES_ORDEN if nombre in clics]
    return "-p anclas_camara:=\"[" + ','.join(partes) + "]\""


def dibujar_rejilla(cv, frame, paso):
    """Superpone una rejilla de coordenadas para leer (x, y) a ojo."""
    if paso <= 0:
        return frame
    alto, ancho = frame.shape[:2]
    for x in range(0, ancho, paso):
        cv.line(frame, (x, 0), (x, alto), (128, 128, 128), 1)
        cv.putText(frame, str(x), (x + 2, 12), cv.FONT_HERSHEY_SIMPLEX,
                   0.35, (0, 255, 255), 1)
    for y in range(0, alto, paso):
        cv.line(frame, (0, y), (ancho, y), (128, 128, 128), 1)
        cv.putText(frame, str(y), (2, y + 12), cv.FONT_HERSHEY_SIMPLEX,
                   0.35, (0, 255, 255), 1)
    return frame


def detectar_colores(frame):
    """Devuelve [(color, x, y)] por cubo detectado. Reutiliza percepcion_camara si está;
    si no, usa el mismo criterio HSV local. Nunca lanza: ante cualquier problema, []."""
    try:
        from arm_broker.percepcion_camara import PercepcionCamara
        return PercepcionCamara()._detectar(frame)
    except Exception:
        pass
    try:
        import cv2 as cv
        hsv = cv.cvtColor(frame, cv.COLOR_BGR2HSV)
        kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (5, 5))
        rangos = {
            'rojo': [((0, 120, 70), (10, 255, 255)), ((170, 120, 70), (180, 255, 255))],
            'amarillo': [((20, 100, 100), (35, 255, 255))],
            'verde': [((40, 70, 70), (85, 255, 255))],
            'azul': [((90, 100, 70), (130, 255, 255))],
        }
        salida = []
        for color, franjas in rangos.items():
            mascara = None
            for bajo, alto in franjas:
                m = cv.inRange(hsv, bajo, alto)
                mascara = m if mascara is None else cv.bitwise_or(mascara, m)
            mascara = cv.morphologyEx(mascara, cv.MORPH_OPEN, kernel)
            mascara = cv.morphologyEx(mascara, cv.MORPH_CLOSE, kernel)
            contornos, _ = cv.findContours(mascara, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
            if not contornos:
                continue
            contorno = max(contornos, key=cv.contourArea)
            if cv.contourArea(contorno) < 300.0:
                continue
            moments = cv.moments(contorno)
            if moments['m00'] == 0:
                continue
            salida.append((color, int(moments['m10'] / moments['m00']),
                           int(moments['m01'] / moments['m00'])))
        return salida
    except Exception:
        return []


def capturar_anotada(cv, cap, paso, espera, guardar):
    """Toma un frame estable (headless), le dibuja rejilla + colores y lo guarda."""
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

    detecciones = detectar_colores(frame)
    for color, x, y in detecciones:
        cv.circle(frame, (x, y), 8, (255, 255, 255), 2)
        cv.putText(frame, color, (x + 10, y), cv.FONT_HERSHEY_SIMPLEX,
                   0.6, (255, 255, 255), 2)
    dibujar_rejilla(cv, frame, paso)

    cv.imwrite(guardar, frame)
    print(f'[CALIBRADOR] foto guardada en: {guardar}')
    print('[CALIBRADOR] centros detectados (x, y):')
    if detecciones:
        for color, x, y in detecciones:
            print(f'    {color}: ({x}, {y})')
    else:
        print('    (ninguno; abre la foto y lee las coordenadas con la rejilla)')
    print('\nAsigna cada esquina a pos1..pos4 (coincidiendo con las poses de poses.py):')
    print('    pos1 = abajo_derecha    pos2 = abajo_izquierda')
    print('    pos3 = arriba_derecha   pos4 = arriba_izquierda')
    print('(tal como se ven en la IMAGEN de la cámara) y pasa la cadena. Ejemplo:')
    print("    -p anclas_camara:=\"['pos1=537,385','pos2=114,380','pos3=520,87','pos4=122,90']\"")


def main():
    ap = argparse.ArgumentParser(description='Calibra las anclas de color de la cámara.')
    ap.add_argument('--indice', type=int, default=None,
                    help='índice de la cámara (por defecto: autodetecta 0..3)')
    ap.add_argument('--guardar', metavar='RUTA', default=None,
                    help='guarda el frame anotado en esta ruta (p. ej. foto_anclas.jpg)')
    ap.add_argument('--mover-brazo', action='store_true',
                    help='manda al broker un goal move_arm hasta POSE_BUSQUEDA antes de abrir la cámara')
    ap.add_argument('--paso', type=float, default=1.5,
                    help='paso de troceado en radianes para ir a POSE_BUSQUEDA (default 1.5)')
    ap.add_argument('--headless', action='store_true',
                    help='sin ventana (no necesita GTK/DISPLAY): guarda una foto anotada y sale')
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
    print('  CALIBRADOR DE ANCLAS DE CÁMARA (Ítem 2)')
    if args.headless:
        print('  MODO HEADLESS: sin ventana; guarda una foto anotada y sale')
        print('  (no necesita GTK ni DISPLAY)')
    else:
        print('  Orden de clic: pos1, pos2, pos3, pos4')
        print('  r=reiniciar  s=guardar  q/ESC=terminar y mostrar anclas')
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
                             args.guardar or 'foto_anclas.jpg')
        finally:
            cap.release()
        return

    ventana = 'calibrar_camara - clic en los cubos (pos1..pos4)'
    clics = {}
    estado = {'frame': None}

    def al_click(evento, x, y, flags, param):
        if evento != cv.EVENT_LBUTTONDOWN:
            return
        for nombre in POSICIONES_ORDEN:
            if nombre not in clics:
                clics[nombre] = (int(x), int(y))
                print(f'  {nombre} = ({x}, {y})')
                break
        else:
            print('  ya están las 4 posiciones; pulsa r para reiniciar')

    cv.namedWindow(ventana)
    cv.setMouseCallback(ventana, al_click)

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            estado['frame'] = frame

            for nombre, (x, y) in clics.items():
                cv.circle(frame, (x, y), 8, (255, 255, 255), 2)
                cv.putText(frame, nombre, (x + 10, y), cv.FONT_HERSHEY_SIMPLEX,
                           0.6, (255, 255, 255), 2)

            faltan = [n for n in POSICIONES_ORDEN if n not in clics]
            pista = f'clic: {faltan[0]}' if faltan else 'completo (q para mostrar anclas)'
            cv.putText(frame, pista, (10, 25), cv.FONT_HERSHEY_SIMPLEX,
                       0.7, (0, 255, 0), 2)
            cv.imshow(ventana, frame)

            tecla = cv.waitKey(1) & 0xFF
            if tecla in (ord('q'), 27):
                break
            if tecla == ord('r'):
                clics.clear()
                print('  reiniciado')
            if tecla == ord('s') and args.guardar:
                cv.imwrite(args.guardar, frame)
                print(f'  foto guardada en {args.guardar}')
    finally:
        cap.release()
        cv.destroyAllWindows()

    if len(clics) == len(POSICIONES_ORDEN):
        print('\nAnclas calibradas:')
        print(cadena_anclas(clics))
    else:
        print(f'\nFaltaron posiciones ({len(clics)}/4); no se generó la cadena completa.')


if __name__ == '__main__':
    main()
