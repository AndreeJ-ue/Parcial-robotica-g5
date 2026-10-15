""" Orquestador COMPLETO del Ítem 2: decisión → cámara → poses → cola del broker → pinza """

""" Reemplaza al orquestador mínimo. Toma la decisión tipada del Ítem 1/3 (/orden_decidida),
rechaza ANTES de encolar lo que no corresponde, localiza el color con la cámara, elige la pose
de agarre y la zona de depósito (poses.py), y manda goals move_arm al broker troceados por paso
articular (para que no los rechace con causa 'paso'), intercalando los comandos de pinza.

Regla dura: el orquestador NUNCA publica /joint_states (solo el broker). Aquí se SUSCRIBE a
/joint_states (lectura) para conocer la pose actual y medir el error de FK, pero jamás publica.

Los goals van en RADIANES (contrato de MoveArm.action); las poses de la mesa están en GRADOS y
se convierten con poses.a_radianes(). El broker es quien vuelve a GRADOS al publicar para el
driver. La prioridad del goal sale del modelo (prioridad × escala_prioridad), nunca escrita a
mano. """

import csv
import json
import os
import threading
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from sensor_msgs.msg import JointState
from std_msgs.msg import String

from arm_broker_interfaces.action import MoveArm

from arm_broker import intentos, poses
from arm_broker.gripper import Pinza
from arm_broker.percepcion_camara import PercepcionCamara


class NodoOrquestador(Node):

    def __init__(self):
        super().__init__('orquestador')

        # Parámetros de ROS 2
        self.declare_parameter('client_id', 'orquestador')
        self.declare_parameter('cliente', 'voz')
        self.declare_parameter('escala_prioridad', 85)
        self.declare_parameter('topico_decision', 'orden_decidida')
        self.declare_parameter('acciones_aceptadas', ['agarrar'])
        self.declare_parameter('paso_orquestador_rad', 1.5)
        self.declare_parameter('timeout_goal_s', 120.0)

        self.declare_parameter('usar_camara', True)
        self.declare_parameter('usar_pose_busqueda', True)
        self.declare_parameter('pose_busqueda', list(poses.POSE_BUSQUEDA))
        self.declare_parameter('espera_busqueda_s', 1.0)
        self.declare_parameter('anclas_camara', [
            'pos1=114,380', 'pos2=537,385', 'pos3=122,90', 'pos4=520,87',
        ])
        self.declare_parameter('radio_ancla_px', 70.0)
        self.declare_parameter('frames_estabilidad', 8)
        self.declare_parameter('timeout_color_s', 8.0)
        self.declare_parameter('indice_camara', -1)
        self.declare_parameter('mapa_color_fijo', [])

        self.declare_parameter('gripper_habilitada', True)
        self.declare_parameter('accion_pinza', 'gripper_command')
        self.declare_parameter('pinza_pos_abierta', float(poses.GRIPPER_ABIERTO))
        self.declare_parameter('pinza_pos_cerrada', float(poses.GRIPPER_CERRADO))
        self.declare_parameter('pinza_puerto', '/dev/ttyUSB0')
        self.declare_parameter('pinza_baudios', 1000000)
        self.declare_parameter('pinza_velocidad', poses.GRIPPER_SPEED)

        self.declare_parameter('archivo_rechazos', 'rechazos_orquestador.csv')
        self.declare_parameter('archivo_intentos', 'intentos.csv')
        self.declare_parameter('archivo_tiempos', 'tiempos_acciones.csv')

        self.identificador = str(self.get_parameter('client_id').value)
        self.cliente = str(self.get_parameter('cliente').value)
        self.escala = int(self.get_parameter('escala_prioridad').value)
        self.acciones_aceptadas = [str(a).lower()
                                   for a in self.get_parameter('acciones_aceptadas').value]
        self.paso = float(self.get_parameter('paso_orquestador_rad').value)
        self.timeout_goal = float(self.get_parameter('timeout_goal_s').value)
        self.ruta_rechazos = str(self.get_parameter('archivo_rechazos').value)
        self.ruta_tiempos = str(self.get_parameter('archivo_tiempos').value)
        self.timeout_color = float(self.get_parameter('timeout_color_s').value)

        self.usar_pose_busqueda = bool(self.get_parameter('usar_pose_busqueda').value)
        self.pose_busqueda = [float(v) for v in self.get_parameter('pose_busqueda').value]
        self.espera_busqueda = float(self.get_parameter('espera_busqueda_s').value)

        self.mapa_fijo = self._leer_mapa_fijo(self.get_parameter('mapa_color_fijo').value)

        # Estado compartido
        self.lock = threading.Lock()
        self.lock_joint = threading.Lock()
        self.cola = []
        self.evento = threading.Event()
        self._parar = threading.Event()
        self.q_actual_deg = None
        self.n_intentos = 0

        self._preparar_rechazos()
        self.registro_intentos = intentos.RegistroIntentos(
            str(self.get_parameter('archivo_intentos').value))

        # Cámara (opcional): si no está, se usa mapa_color_fijo
        self.camara = None
        if bool(self.get_parameter('usar_camara').value):
            self.camara = PercepcionCamara(
                anclas=self._leer_anclas(self.get_parameter('anclas_camara').value),
                radio_ancla=float(self.get_parameter('radio_ancla_px').value),
                indice_camara=(None if int(self.get_parameter('indice_camara').value) < 0
                               else int(self.get_parameter('indice_camara').value)),
                frames_estabilidad=int(self.get_parameter('frames_estabilidad').value))
            self.camara.iniciar()

        # Pinza (vía primaria: acción gripper_command; respaldo: pymycobot)
        self.pinza = Pinza(
            self,
            habilitada=bool(self.get_parameter('gripper_habilitada').value),
            accion=str(self.get_parameter('accion_pinza').value),
            pos_abierta=float(self.get_parameter('pinza_pos_abierta').value),
            pos_cerrada=float(self.get_parameter('pinza_pos_cerrada').value),
            puerto=str(self.get_parameter('pinza_puerto').value),
            baudios=int(self.get_parameter('pinza_baudios').value),
            velocidad=int(self.get_parameter('pinza_velocidad').value))

        # ROS: cliente de la acción, suscripción a la decisión y a la pose actual (solo lectura)
        grupo = ReentrantCallbackGroup()
        self.accion = ActionClient(self, MoveArm, 'move_arm', callback_group=grupo)
        self.suscripcion = self.create_subscription(
            String, str(self.get_parameter('topico_decision').value),
            self._al_recibir, 10, callback_group=grupo)
        self.suscripcion_joint = self.create_subscription(
            JointState, '/joint_states', self._al_joint_state, 10, callback_group=grupo)

        self.hilo = threading.Thread(target=self._worker, daemon=True)
        self.hilo.start()

        self.get_logger().info('=' * 60)
        self.get_logger().info('  ORQUESTADOR ÍTEM 2 LISTO')
        self.get_logger().info(f'  pasos cubo   : {sorted(poses.POSICIONES_CUBO)}')
        self.get_logger().info(f'  destinos     : {sorted(poses.DESTINOS)}')
        self.get_logger().info(f'  troceo       : paso <= {self.paso:.2f} rad')
        self.get_logger().info(f'  pinza        : {self.pinza.via or "por descubrir"}')
        self.get_logger().info('  /joint_states: solo LECTURA (nunca publica)')
        self.get_logger().info('=' * 60)

    # 1. Utilidades de parámetros
    @staticmethod
    def _leer_anclas(lista):
        anclas = {}
        for item in lista:
            if '=' not in item:
                continue
            nombre, valores = item.split('=', 1)
            partes = valores.split(',')
            if len(partes) != 2:
                continue
            try:
                anclas[nombre.strip().lower()] = (float(partes[0]), float(partes[1]))
            except ValueError:
                continue
        return anclas

    @staticmethod
    def _leer_mapa_fijo(lista):
        mapa = {}
        for item in lista:
            if '=' not in item:
                continue
            color, posicion = item.split('=', 1)
            mapa[color.strip().lower()] = posicion.strip().lower()
        return mapa

    def _preparar_rechazos(self):
        if not os.path.exists(self.ruta_rechazos):
            with open(self.ruta_rechazos, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([
                    't_unix', 'client_id', 'priority', 'causa', 'motivo', 'frase',
                ])
        if not os.path.exists(self.ruta_tiempos):
            with open(self.ruta_tiempos, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([
                    't_unix', 'frase', 'intento', 'meta', 'prioridad',
                    't_envio', 't_fin', 'wait_time_s', 'exec_time_s', 'exito',
                ])

    # 2. Rechazo antes de encolar
    def _rechazar(self, decision, causa, motivo):
        with open(self.ruta_rechazos, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                f'{time.time():.3f}', self.identificador,
                int(decision.get('prioridad', 0)), causa, motivo, decision.get('frase', ''),
            ])
        self.get_logger().warn(
            f'⛔ RECHAZADA ANTES DE ENCOLAR ({causa}): '
            f'"{decision.get("frase", "")}" — {motivo}')

    # 3. Pose actual (solo lectura de /joint_states; el broker la publica en GRADOS)
    def _al_joint_state(self, msg):
        with self.lock_joint:
            self.q_actual_deg = [float(v) for v in msg.position]

    def _q_actual_grados(self):
        with self.lock_joint:
            q = None if self.q_actual_deg is None else list(self.q_actual_deg)
        return q if q is not None else [0.0] * 6

    # 4. Recepción de la decisión
    def _al_recibir(self, msg):
        try:
            decision = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error(f'decisión inválida (no es JSON): {msg.data!r}')
            return

        if not decision.get('permitido', False):
            self._rechazar(decision, 'no_permitida',
                           decision.get('motivo') or 'el modelo marcó permitido=False')
            return

        objeto = str(decision.get('objeto', 'desconocido')).lower()
        color = str(decision.get('color', 'ninguno')).lower()
        accion = str(decision.get('accion', 'desconocido')).lower()

        if objeto in ('desconocido', '') or color in ('ninguno', ''):
            self._rechazar(decision, 'objeto_desconocido',
                           'objeto o color no reconocidos; no hay pose de agarre')
            return
        if accion not in self.acciones_aceptadas:
            self._rechazar(decision, 'accion_no_soportada',
                           f"la acción '{accion}' no es de agarre")
            return
        if color not in poses.DESTINOS:
            self._rechazar(decision, 'color_sin_destino',
                           f'no hay zona de depósito definida para {color}')
            return

        prioridad = max(0, min(255, int(decision.get('prioridad', 0)) * self.escala))
        item = dict(decision)
        item['_priority'] = prioridad

        with self.lock:
            self.cola.append(item)
            self.cola.sort(key=lambda d: -d['_priority'])
        self.evento.set()
        self.get_logger().info(
            f'📥 ENCOLADA p{prioridad} ({len(self.cola)} en espera): '
            f'"{decision.get("frase", "")}"')

    # 5. Worker: una secuencia de agarre a la vez
    def _worker(self):
        while not self._parar.is_set():
            with self.lock:
                item = self.cola.pop(0) if self.cola else None
            if item is None:
                self.evento.wait(0.2)
                self.evento.clear()
                continue
            self.get_logger().info(
                f'▶️  DESENCOLADA p{item["_priority"]}: "{item.get("frase", "")}"')
            try:
                self._procesar(item)
            except Exception as e:
                self.get_logger().error(f'error procesando la orden: {e!r}')

    # 6. Pose de búsqueda: coloca la cámara (montada en el brazo) frente a la mesa
    def _ir_a_busqueda(self, prioridad):
        if not self.usar_pose_busqueda:
            return
        if self.camara is None or not self.camara.disponible:
            return
        origen_rad = poses.a_radianes(self._q_actual_grados())
        metas = poses.trozar(origen_rad, poses.a_radianes(self.pose_busqueda), self.paso)
        self.get_logger().info('🔎 POSE_BUSQUEDA: colocando la cámara frente a la mesa')
        for q_rad in metas:
            exito, motivo, _, _ = self._enviar_goal(q_rad, prioridad)
            if not exito:
                self.get_logger().warn(f'no se alcanzó POSE_BUSQUEDA: {motivo}')
                return
        if self.espera_busqueda > 0.0:
            time.sleep(self.espera_busqueda)

    # 6b. Ubicación del color con cámara (o mapa fijo de respaldo)
    def _ubicar(self, color):
        if self.camara is not None and self.camara.disponible:
            posicion = self.camara.esperar_color(color, self.timeout_color)
            if posicion is not None:
                return posicion
            self.get_logger().warn(
                f'la cámara no vio un cubo {color} estable; pruebo mapa_color_fijo')

        posicion = self.mapa_fijo.get(color)
        if posicion in poses.POSICIONES_CUBO:
            self.get_logger().info(f'mapa_color_fijo: {color} -> {posicion}')
            return posicion
        return None

    # 7. Secuencia completa de un pedido
    def _procesar(self, decision):
        color = str(decision.get('color', '')).lower()
        objeto = str(decision.get('objeto', '')).lower()
        frase = decision.get('frase', '')
        prioridad = decision['_priority']

        self._ir_a_busqueda(prioridad)

        posicion = self._ubicar(color)
        if posicion is None:
            self._rechazar(decision, 'no_detectado',
                           f'no se encontró el cubo {color} sobre la mesa')
            return

        meta_cubo = poses.pose_cubo(posicion)
        meta_destino = poses.pose_destino(color)
        if meta_cubo is None or meta_destino is None:
            self._rechazar(decision, 'sin_pose', f'sin pose para {color} en {posicion}')
            return

        self.n_intentos += 1
        intento = self.n_intentos
        self.get_logger().info(
            f'🤖 Intento {intento}: {color} en {posicion} → zona {color}')

        exito, motivo, q_alcanzada_rad = self._secuencia(
            decision, intento, meta_cubo, meta_destino, prioridad)

        self.registro_intentos.registrar(
            intento, frase, objeto, color, posicion, color, exito,
            poses.a_radianes(meta_destino), q_alcanzada_rad, motivo)
        self.get_logger().info(
            f'🏁 Intento {intento}: exito={exito} ({motivo or "ok"})')

    def _secuencia(self, decision, intento, meta_cubo, meta_destino, prioridad):
        abierta = self.pinza.abrir()
        if not abierta:
            self.get_logger().warn('la pinza no abrió; continúo el movimiento')

        if not self._mover_hacia(decision, intento, meta_cubo, prioridad):
            self._volver_a_casa(decision, intento, prioridad)
            return False, 'no se alcanzó la posición de agarre', None

        if not self.pinza.cerrar():
            self.get_logger().warn('la pinza no cerró; el cubo podría caerse')

        if not self._mover_hacia(decision, intento, meta_destino, prioridad):
            self._volver_a_casa(decision, intento, prioridad)
            return False, 'no se alcanzó la zona de depósito', None

        q_alcanzada_rad = poses.a_radianes(self._q_actual_grados())
        self.pinza.abrir()
        self._volver_a_casa(decision, intento, prioridad)
        return True, '', q_alcanzada_rad

    def _volver_a_casa(self, decision, intento, prioridad):
        if not self._mover_hacia(decision, intento, poses.POSE_HOME, prioridad, silencioso=True):
            self.get_logger().warn('no se pudo volver a POSE_HOME')

    # 8. Movimiento troceado
    def _mover_hacia(self, decision, intento, meta_grados, prioridad, silencioso=False):
        origen_rad = poses.a_radianes(self._q_actual_grados())
        metas = poses.trozar(origen_rad, poses.a_radianes(meta_grados), self.paso)

        for indice, q_rad in enumerate(metas, start=1):
            t_envio = time.time()
            exito, motivo, wait_s, exec_s = self._enviar_goal(q_rad, prioridad)
            self._anotar_tiempo(decision, intento, indice, prioridad,
                                t_envio, time.time(), wait_s, exec_s, exito)
            if not exito:
                if not silencioso:
                    self.get_logger().warn(
                        f'meta {indice}/{len(metas)} falló: {motivo}')
                return False
        return True

    # 9. Envío de un goal al broker
    def _enviar_goal(self, q_rad, prioridad):
        if not self.accion.wait_for_server(timeout_sec=10.0):
            return False, 'el broker no aparece (¿está corriendo arm_broker?)', 0.0, 0.0

        goal = MoveArm.Goal()
        goal.joint_positions = [float(v) for v in q_rad]
        goal.client_id = self.identificador
        goal.priority = int(prioridad)

        self.get_logger().info(
            f'   ➡️  goal p{prioridad}: '
            f'{[round(v, 2) for v in q_rad]} rad')

        envio = self.accion.send_goal_async(goal)
        if not self._esperar(envio, 10.0):
            return False, 'timeout enviando el goal', 0.0, 0.0
        handle = envio.result()
        if handle is None or not handle.accepted:
            return False, 'el broker RECHAZÓ el goal (ver rechazos.csv del broker)', 0.0, 0.0

        resultado = handle.get_result_async()
        if not self._esperar(resultado, self.timeout_goal):
            return False, 'el broker no devolvió resultado', 0.0, 0.0
        r = resultado.result().result
        return bool(r.success), r.message, float(r.wait_time_s), float(r.exec_time_s)

    @staticmethod
    def _esperar(futuro, timeout_s):
        t0 = time.time()
        while not futuro.done():
            if time.time() - t0 > timeout_s:
                return False
            time.sleep(0.02)
        return True

    # 10. Registro de tiempos por meta
    def _anotar_tiempo(self, decision, intento, meta, prioridad,
                       t_envio, t_fin, wait_s, exec_s, exito):
        with open(self.ruta_tiempos, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                f'{t_envio:.3f}', decision.get('frase', ''), intento, meta, prioridad,
                f'{t_envio:.3f}', f'{t_fin:.3f}',
                f'{wait_s:.3f}', f'{exec_s:.3f}', bool(exito),
            ])

    # 11. Cierre
    def destroy_node(self):
        self._parar.set()
        self.evento.set()
        if self.camara is not None:
            self.camara.detener()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    nodo = NodoOrquestador()
    ejecutor = MultiThreadedExecutor(num_threads=4)
    ejecutor.add_node(nodo)
    try:
        ejecutor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
