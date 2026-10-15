#!/usr/bin/env python3
""" Calibrador de anclas de cámara del Ítem 2 — ver y extraer las posiciones de los cubos.

Para qué sirve: la cámara está montada EN EL BRAZO, así que solo ve bien la mesa cuando el
brazo está en POSE_BUSQUEDA. Con el brazo en esa pose, este script abre la cámara a 640x480,
muestra la imagen en vivo y deja que ustedes hagan CLIC en los cuatro cubos, en orden
pos1, pos2, pos3, pos4. Al terminar imprime la cadena exacta para copiar en el orquestador:

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
    args = ap.parse_args()

    try:
        import cv2 as cv
    except ImportError:
        sys.exit('FALLO: falta OpenCV. Instala python3-opencv (Jetson) o pip install opencv-python.')

    print('=' * 64)
    print('  CALIBRADOR DE ANCLAS DE CÁMARA (Ítem 2)')
    print('  Orden de clic: pos1, pos2, pos3, pos4')
    print('  r=reiniciar  s=guardar  q/ESC=terminar y mostrar anclas')
    print('=' * 64)

    if args.mover_brazo:
        if not mover_brazo_a_busqueda(paso_rad=args.paso):
            print('[CALIBRADOR] continúo SIN mover el brazo (ponlo a mano en POSE_BUSQUEDA)')

    cap = abrir_camara(cv, args.indice)
    if cap is None:
        sys.exit('FALLO: no se encontró cámara disponible.')

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
