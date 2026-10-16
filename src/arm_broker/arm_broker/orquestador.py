""" Orquestador de la cadena de agarre autónomo — Ítem 2 (Pregunta 2) """

""" Puente entre la decisión tipada (Ítem 1/3) y el broker del RB-2, con la regla de oro: SOLO
el worker del broker publica comandos al brazo. Este nodo no publica /joint_states: solo escucha
la decisión, espera la confirmación de la cámara, elige la pose de la ESTACIÓN donde se vio el
color (4 estaciones — ver estaciones.py), y manda la secuencia de goals a la acción move_arm (con
la prioridad del modelo) intercalando los comandos de pinza.

El tapete tiene CUATRO estaciones y un cubo por color en cualquier estación. La cámara publica el
mapa {estación → color} y aquí se resuelve la estación del color pedido; si el color no está en
ninguna, se rechaza con causa 'color_no_encontrado'.

Hay exactamente 3 acciones (ver tabla). 'mover' es la única con una decisión real: si el brazo YA
tiene un cubo en mano (self.cargando, de una 'agarrar' anterior) no repite el agarre, solo
completa el transporte; si no tiene nada, hace el pick-and-place completo.

Acción  | ¿color? | Secuencia
agarrar | sí      | busqueda → cámara resuelve estación → abrir→AGARRE[est]→cerrar → busqueda
soltar  | no      | abre la pinza donde esté, sin mover el brazo
mover   | sí      | si self.cargando: reparto→destino[color]→abrir→home (NO vuelve a agarrar)
        |         | si no: busqueda → estación → agarre completo → transporte → home
detener | no      | limpia la cola de pendientes y vuelve a home

Unidades: los goals van en RADIANES (contrato de MoveArm.action); las poses de la mesa están en
GRADOS y se convierten con poses.a_radianes(). El broker publica /joint_states en GRADOS (contrato
con el driver del kit), así que aquí se vuelve a RADIANES al LEER para medir el error de FK. """

import csv
import json
import math
import os
import queue
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

from arm_broker import intentos, poses, estaciones
from arm_broker.gripper import Pinza


class NodoOrquestador(Node):

    def __init__(self):
        super().__init__('orquestador')

        self.declare_parameter('client_id', 'orquestador')
        self.declare_parameter('escala_prioridad', 85)      # priority = prioridad * 85 (0..3 → 0..255)
        self.declare_parameter('paso_orquestador_rad', 1.0)  # <= paso_max_rad del broker (1.2)
        self.declare_parameter('usar_camara', True)
        self.declare_parameter('usar_estaciones', True)      # True = mapa {estación: color}; False = pose única
        self.declare_parameter('espera_deteccion_s', 6.0)
        self.declare_parameter('timeout_goal_s', 60.0)

        self.declare_parameter('gripper_habilitada', True)
        self.declare_parameter('accion_pinza', 'gripper_command')
        self.declare_parameter('pinza_pos_abierta', float(poses.GRIPPER_ABIERTO))
        self.declare_parameter('pinza_pos_cerrada', float(poses.GRIPPER_CERRADO))
        self.declare_parameter('pinza_esfuerzo', 10.0)
        self.declare_parameter('pinza_puerto', '/dev/ttyUSB0')
        self.declare_parameter('pinza_baudios', 1000000)
        self.declare_parameter('pinza_velocidad', poses.GRIPPER_SPEED)

        self.declare_parameter('topico_decision', 'orden_decidida')
        self.declare_parameter('topico_deteccion', 'objeto_detectado')
        self.declare_parameter('archivo_rechazos', 'rechazos_orquestador.csv')
        self.declare_parameter('archivo_intentos', 'intentos.csv')
        self.declare_parameter('archivo_tiempos', 'tiempos_acciones.csv')

        self.identificador = str(self.get_parameter('client_id').value)
        self.escala = int(self.get_parameter('escala_prioridad').value)
        self.paso = float(self.get_parameter('paso_orquestador_rad').value)
        self.usar_camara = bool(self.get_parameter('usar_camara').value)
        self.usar_estaciones = bool(self.get_parameter('usar_estaciones').value)
        self.espera_deteccion = float(self.get_parameter('espera_deteccion_s').value)
        self.timeout_goal = float(self.get_parameter('timeout_goal_s').value)
        self.ruta_rechazos = str(self.get_parameter('archivo_rechazos').value)
        self.ruta_tiempos = str(self.get_parameter('archivo_tiempos').value)

        self._preparar_csv()
        self.registro_intentos = intentos.RegistroIntentos(
            str(self.get_parameter('archivo_intentos').value))

        # sin_camara no hay respaldo: si el mapa no aparece, la orden se rechaza
        self.pinza = Pinza(
            self,
            habilitada=bool(self.get_parameter('gripper_habilitada').value),
            accion=str(self.get_parameter('accion_pinza').value),
            pos_abierta=float(self.get_parameter('pinza_pos_abierta').value),
            pos_cerrada=float(self.get_parameter('pinza_pos_cerrada').value),
            esfuerzo=float(self.get_parameter('pinza_esfuerzo').value),
            puerto=str(self.get_parameter('pinza_puerto').value),
            baudios=int(self.get_parameter('pinza_baudios').value),
            velocidad=int(self.get_parameter('pinza_velocidad').value))

        grupo = ReentrantCallbackGroup()
        self.accion = ActionClient(self, MoveArm, 'move_arm', callback_group=grupo)
        self.create_subscription(String, str(self.get_parameter('topico_decision').value),
                                 self._al_recibir, 10, callback_group=grupo)
        self.create_subscription(String, str(self.get_parameter('topico_deteccion').value),
                                 self._al_deteccion, 10, callback_group=grupo)
        # SOLO LECTURA: captura la pose alcanzada para el error de FK (nunca publica)
        self.create_subscription(JointState, '/joint_states', self._al_joint, 10,
                                 callback_group=grupo)

        self.lock = threading.Lock()
        self.lock_joint = threading.Lock()
        self.q_actual = [0.0] * 6
        self.deteccion = None
        self.cola = queue.Queue()
        self.evento = threading.Event()
        self._parar = threading.Event()
        self.n_intentos = 0
        self.cargando = False

        self.hilo = threading.Thread(target=self._worker, daemon=True)
        self.hilo.start()

        self.get_logger().info('=' * 60)
        self.get_logger().info('  ORQUESTADOR ÍTEM 2 LISTO')
        self.get_logger().info(f'  estaciones   : {sorted(estaciones.ESTACIONES)}')
        self.get_logger().info(f'  destinos     : {sorted(poses.DESTINOS)}')
        self.get_logger().info(f'  troceo       : paso <= {self.paso:.2f} rad')
        self.get_logger().info(f'  usar_camara  : {self.usar_camara} · estaciones: {self.usar_estaciones}')
        self.get_logger().info(f'  pinza        : {self.pinza.via or "por descubrir"}')
        self.get_logger().info('  /joint_states: solo LECTURA (nunca publica)')
        self.get_logger().info('=' * 60)

    # 1. CSVs y utilidades
    def _preparar_csv(self):
        if not os.path.exists(self.ruta_rechazos):
            with open(self.ruta_rechazos, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([
                    't_unix', 'client_id', 'priority', 'causa', 'motivo', 'frase',
                ])
        if not os.path.exists(self.ruta_tiempos):
            with open(self.ruta_tiempos, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([
                    't_unix', 'frase', 'intento', 'meta', 'prioridad',
                    'wait_time_s', 'exec_time_s', 'exito',
                ])

    @staticmethod
    def _esperar(futuro, timeout):
        evento = threading.Event()
        futuro.add_done_callback(lambda _: evento.set())
        if not evento.wait(timeout):
            return None
        return futuro.result()

    # 2. Callbacks de suscripción
    def _al_joint(self, msg):
        with self.lock_joint:
            if len(msg.position) >= 6:
                # /joint_states llega en GRADOS (contrato con el driver); internamente radianes.
                self.q_actual = [math.radians(float(v)) for v in msg.position[:6]]

    def _al_deteccion(self, msg):
        try:
            datos = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        with self.lock:
            self.deteccion = datos

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
        with self.lock:
            self.cola.put(decision)
        self.evento.set()
        self.get_logger().info(
            f'📥 ENCOLADA ({self.cola.qsize()} en espera): "{decision.get("frase", "")}"')

    def _rechazar(self, decision, causa, motivo):
        with open(self.ruta_rechazos, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                f'{time.time():.3f}', self.identificador,
                int(decision.get('prioridad', 0)), causa, motivo, decision.get('frase', ''),
            ])
        self.get_logger().warn(
            f'⛔ RECHAZADA ({causa}): "{decision.get("frase", "")}" — {motivo}')

    # 3. Worker: una orden completa a la vez
    def _worker(self):
        while not self._parar.is_set():
            try:
                decision = self.cola.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._atender(decision)
            except Exception as e:
                self.get_logger().error(f'error atendiendo la orden: {e!r}')

    # 4. Espera de la confirmación visual del color / de la estación
    def _snapshot_deteccion(self):
        with self.lock:
            return dict(self.deteccion) if self.deteccion else None

    def _mapa_estaciones(self):
        """Devuelve {estación:int → color:str} de la última detección, o {} si no hay nada."""
        det = self._snapshot_deteccion()
        if not det:
            return {}
        bruto = det.get('mapa_estaciones') or {}
        mapa = {}
        for e, c in bruto.items():
            try:
                mapa[int(e)] = c
            except (TypeError, ValueError):
                continue
        return mapa

    def _esperar_estacion(self, color):
        """Espera a que el MAPA estable {estación → color} contenga `color` y devuelve la
        estación (1..4). None si en espera_deteccion_s no apareció en ninguna estación."""
        limite = time.time() + self.espera_deteccion
        while time.time() < limite and rclpy.ok():
            det = self._snapshot_deteccion()
            if det and det.get('estable'):
                for e, c in (det.get('mapa_estaciones') or {}).items():
                    if c == color:
                        try:
                            return int(e)
                        except (TypeError, ValueError):
                            continue
            time.sleep(0.05)
        return None

    def _esperar_color(self, color):
        """Modo legacy: espera una detección ESTABLE del color (sin importar estación)."""
        limite = time.time() + self.espera_deteccion
        while time.time() < limite and rclpy.ok():
            det = self._snapshot_deteccion()
            if (det and det.get('presente') and det.get('color') == color
                    and det.get('estable')):
                return det
            time.sleep(0.05)
        return None

    # 5. Envío de un movimiento al broker (una meta, ya troceada por poses.trozar)
    def _enviar_goal(self, q_rad, prioridad):
        if not self.accion.wait_for_server(timeout_sec=10.0):
            return False, 'el broker no aparece (¿está corriendo arm_broker?)', 0.0, 0.0
        goal = MoveArm.Goal()
        goal.joint_positions = [float(v) for v in q_rad]
        goal.client_id = self.identificador
        goal.priority = int(prioridad)
        envio = self._esperar(self.accion.send_goal_async(goal), 10.0)
        if envio is None:
            return False, 'timeout enviando el goal', 0.0, 0.0
        handle = envio
        if handle is None or not handle.accepted:
            return False, 'el broker RECHAZÓ el goal (ver rechazos.csv del broker)', 0.0, 0.0
        resultado = self._esperar(handle.get_result_async(), self.timeout_goal)
        if resultado is None:
            return False, 'el broker no devolvió resultado', 0.0, 0.0
        r = resultado.result
        return bool(r.success), r.message, float(r.wait_time_s), float(r.exec_time_s)

    def _mover_a(self, grados, prioridad, decision=None, intento=None):
        """Mueve hacia la pose destino (grados), troceando en metas que respeten self.paso.
        Devuelve True si TODAS las metas se alcanzaron."""
        destino = poses.a_radianes(grados)
        with self.lock_joint:
            origen = list(self.q_actual)
        for indice, meta in enumerate(poses.trozar(origen, destino, self.paso), start=1):
            t_envio = time.time()
            exito, motivo, wait_s, exec_s = self._enviar_goal(meta, prioridad)
            if decision is not None:
                self._anotar_tiempo(decision, intento, indice, prioridad,
                                    t_envio, wait_s, exec_s, exito)
            self.get_logger().info(
                f'   ➡️  meta {indice} p{int(prioridad)} {[round(v, 2) for v in meta]} rad',
                throttle_duration_sec=0.2)
            if not exito:
                self.get_logger().warn(f'   meta {indice} falló: {motivo}')
                return False
            with self.lock_joint:
                origen = list(self.q_actual)
        return True

    # 6. Atención de una decisión válida (despacho por acción)
    def _atender(self, decision):
        frase = decision.get('frase', '')
        accion = str(decision.get('accion') or 'desconocido').lower()
        objeto = decision.get('objeto', 'desconocido')
        color = str(decision.get('color') or 'ninguno').lower()
        motivo = decision.get('motivo', '')

        if not decision.get('permitido', False):
            self._rechazar(decision, 'no_permitida', motivo or 'el modelo marcó permitido=False')
            return

        if accion == 'detener':
            self._detener()
            return

        tiene_color = color not in ('', 'ninguno')
        if accion not in ('agarrar', 'soltar', 'mover'):
            self._rechazar(decision, 'accion_desconocida',
                           f'la acción {accion!r} no se reconoce; no hay nada que ejecutar')
            return
        if accion != 'soltar' and (objeto == 'desconocido' or not tiene_color):
            self._rechazar(decision, 'objeto_desconocido',
                           'objeto o color no reconocidos; no hay pose de agarre')
            return
        if accion != 'soltar' and poses.pose_destino(color) is None:
            self._rechazar(decision, 'color_sin_destino',
                           f'no hay zona de depósito definida para {color}')
            return

        prioridad = max(0, min(255, int(decision.get('prioridad', 0)) * self.escala))

        if accion == 'soltar':
            self.n_intentos += 1
            intento = self.n_intentos
            self.get_logger().info(f'▶️  intento {intento}: "{frase}" accion=soltar')
            self._ejecutar_accion(decision, intento, poses.secuencia_soltar(), prioridad,
                                  medir_agarre=False, cargando=False,
                                  zona='soltar')
            return

        continuar_cargado = (accion == 'mover' and self.cargando)

        estacion = None
        if not continuar_cargado:
            # 'agarrar' y 'mover' desde cero van a POSE_BUSQUEDA y esperan que la cámara
            # confirme el color ANTES de moverse más.
            self.get_logger().info('🔎 yendo a POSE_BUSQUEDA (espacio de detección)')
            if self.usar_camara and not self._mover_a(poses.POSE_BUSQUEDA, prioridad,
                                                      decision, self.n_intentos + 1):
                self._rechazar(decision, 'fallo_movimiento',
                               'no se pudo llegar a POSE_BUSQUEDA (revisa rechazos.csv del '
                               'broker y que arm_broker esté corriendo)')
                return
            if self.usar_camara and self.usar_estaciones:
                estacion = self._esperar_estacion(color)
                if estacion is None:
                    self._rechazar(decision, 'color_no_encontrado',
                                   f'la cámara no vio el color {color} en ninguna estación '
                                   f'(mapa={self._mapa_estaciones()})')
                    return
                self.get_logger().info(f'📍 color {color} en estación {estacion} '
                                       f'(mapa={self._mapa_estaciones()})')
            elif self.usar_camara:
                if self._esperar_color(color) is None:
                    self._rechazar(decision, 'sin_deteccion',
                                   f'la cámara no confirmó un objeto {color} estable sobre la mesa')
                    return

        self.n_intentos += 1
        intento = self.n_intentos
        self.get_logger().info(
            f'▶️  intento {intento}: "{frase}" accion={accion} ({objeto}/{color}) '
            f'priority={prioridad} cargando={self.cargando} estacion={estacion}')

        zona = f'est{estacion}_{color}' if estacion else f'zona_{color}'
        if accion == 'agarrar':
            self._ejecutar_accion(decision, intento, poses.secuencia_agarrar(estacion), prioridad,
                                  medir_agarre=True, cargando=True,
                                  agarre_grados=poses.agarre(estacion), zona=zona)
        elif continuar_cargado:
            self._ejecutar_accion(decision, intento, poses.secuencia_transportar(color), prioridad,
                                  medir_agarre=False, cargando=False,
                                  zona=f'transporte_{color}')
        else:
            self._ejecutar_accion(decision, intento,
                                  poses.secuencia_completa(color, estacion), prioridad,
                                  medir_agarre=True, cargando=False,
                                  agarre_grados=poses.agarre(estacion), zona=zona)

    # 7. Ejecución de un plan
    def _ejecutar_accion(self, decision, intento, pasos, prioridad, medir_agarre, cargando,
                         agarre_grados=None, zona=None):
        """Ejecuta los pasos del plan, registra el intento y actualiza el estado de carga.

        agarre_grados: pose de agarre realmente pedida (la de la estación); si es None se mide
        contra POSE_RECOGIDA (respaldo). zona: etiqueta para intentos.csv (p.ej. est3_verde)."""
        q_agarre_pedida = poses.a_radianes(agarre_grados or poses.POSE_RECOGIDA)
        q_agarre_alcanzada = list(q_agarre_pedida)
        exito = True

        for paso in pasos:
            if paso[0] == 'gripper':
                if self.pinza.habilitada:
                    ok = self.pinza.abrir() if paso[1] == 'abrir' else self.pinza.cerrar()
                else:
                    self.get_logger().warn(
                        f'🖐  pinza SIMULADA ({paso[1]}): gripper_habilitada=false',
                        throttle_duration_sec=2.0)
                    ok = True
            else:
                ok = self._mover_a(paso[2], prioridad, decision, intento)
                if paso[1] == 'agarre':
                    with self.lock_joint:
                        q_agarre_alcanzada = list(self.q_actual)
            if not ok:
                exito = False
                break

        # Si falló a mitad, intentar volver a home en el mejor esfuerzo (evita dejar el brazo
        # colgando sobre la mesa).
        if not exito and not self._parar.is_set():
            self._mover_a(poses.POSE_HOME, prioridad)

        # Bug corregido respecto al diseño de referencia: 'cargando' solo queda True si el
        # agarre terminó bien; un agarre fallido NO debe dejar el estado como si hubiera cubo.
        self.cargando = bool(cargando and exito)

        frase = decision.get('frase', '')
        objeto = decision.get('objeto', 'desconocido')
        color = str(decision.get('color') or 'ninguno').lower()
        motivo = 'ok' if exito else 'secuencia incompleta'
        self.registro_intentos.registrar(
            intento, frase, objeto, color, zona or f'zona_{color}', color, exito,
            q_agarre_pedida, q_agarre_alcanzada, motivo)
        self.get_logger().info(
            f'🏁 intento {intento}: exito={exito} (cargando={self.cargando})')

    def _anotar_tiempo(self, decision, intento, meta, prioridad, t_envio, wait_s, exec_s, exito):
        with open(self.ruta_tiempos, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                f'{t_envio:.3f}', decision.get('frase', ''), intento, meta, prioridad,
                f'{wait_s:.3f}', f'{exec_s:.3f}', bool(exito),
            ])

    def _detener(self):
        """Limpia la cola de pendientes y regresa el brazo a HOME."""
        vaciados = 0
        while True:
            try:
                self.cola.get_nowait()
                vaciados += 1
            except queue.Empty:
                break
        self.get_logger().info(
            f'⏹️  DETENER: cola limpiada ({vaciados} órdenes descartadas); vuelvo a HOME')
        self._mover_a(poses.POSE_HOME, 0)
        self.cargando = False

    # 8. Cierre
    def destroy_node(self):
        self._parar.set()
        self.evento.set()
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
