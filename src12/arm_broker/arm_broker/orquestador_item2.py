""" Orquestador de la cadena de agarre autónomo — Pregunta 2 """

""" Puente entre la decisión tipada (Pregunta 1) y el broker del RB-2, con la regla de oro:
SOLO el worker del broker publica comandos al brazo. Este nodo no publica /joint_states:
únicamente escucha la decisión, espera la confirmación de la cámara, elige la pose de la
POSICIÓN donde se vio el color (4 posiciones — ver zonas.py), y envía la secuencia de goals a
la acción move_arm (con la prioridad del modelo) y a la pinza.

Sobre la mesa hay un espacio delimitado con CUATRO posiciones conocidas y un cubo por color en
cualquier posición. La cámara publica el mapa {slot: color} y aquí se resuelve el slot del color
pedido; si el color no está en ninguna posición se rechaza con causa 'color_no_encontrado'.

Hay exactamente 3 acciones (ver tabla abajo). 'mover' es la única con una decisión real: si
el brazo YA tiene un cubo en mano (self.cargando, de una 'agarrar' anterior) no repite el
agarre, solo completa el tramo de transporte; si no tiene nada, hace el pick-and-place completo.

Acción    | Requiere color | Secuencia
agarrar   | sí             | busqueda → cámara resuelve slot → abrir→RECOGIDA[slot]→cerrar → busqueda
soltar    | no             | abre la pinza donde esté, sin mover el brazo
mover     | sí             | si self.cargando: reparto→destino[color]→abrir→home (NO vuelve a agarrar)
          |                | si no: busqueda → slot → agarre completo → transporte → home
detener   | no             | limpia la cola de pendientes y vuelve a home

PARCHE_COMPENSACION_MOTOR.md (de la carpeta CLAUDE/) proponía dividir por un 'factor_motor';
aquí NO se usa: el broker publica /joint_states en GRADOS (contrato con el driver del kit:
sync_plan_nx pasa el valor tal cual a send_angles de pymycobot, que usa grados). En
_on_joint_states se vuelve a RADIANES al leer, para que self.q_actual (y el error de FK en
intentos.csv) sea siempre radianes reales. ver CAMBIOS_GRADOS_Y_GRIPPER.md """

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

from arm_broker import intentos as intentos_mod
from arm_broker import poses as poses_mod
from arm_broker.gripper import Pinza


class OrquestadorItem2(Node):

    def __init__(self):
        super().__init__('orquestador_item2')

        self.declare_parameter('client_id', 'p2')
        self.declare_parameter('escala_prioridad', 85)         # priority = prioridad * 85 (0..3 → 0..255)
        self.declare_parameter('paso_max_rad', 1.6)            # trocea los movimientos largos
        self.declare_parameter('usar_camara', True)            # si no, confía en la decisión
        self.declare_parameter('usar_zonas', True)             # True = 4 posiciones (mapa {slot: color}); False = pose única legacy
        self.declare_parameter('espera_deteccion_s', 3.0)
        self.declare_parameter('timeout_goal_s', 30.0)
        self.declare_parameter('gripper_action', 'gripper_command')
        self.declare_parameter('gripper_abierto', 0.0)
        self.declare_parameter('gripper_cerrado', 0.04)
        self.declare_parameter('gripper_esfuerzo', 50.0)
        self.declare_parameter('gripper_habilitada', True)     # False = simula la pinza (demo sin pinza lista)
        self.declare_parameter('gripper_timeout_s', 5.0)       # PROPIO: no reusar timeout_goal_s (30 s)
        self.declare_parameter('topico_decision', 'orden_decidida')
        self.declare_parameter('topico_deteccion', 'objeto_detectado')
        self.declare_parameter('archivo_rechazos', 'rechazos_orquestador.csv')
        self.declare_parameter('archivo_intentos', 'intentos.csv')

        self.client_id = str(self.get_parameter('client_id').value)
        self.escala = int(self.get_parameter('escala_prioridad').value)
        self.paso_max = float(self.get_parameter('paso_max_rad').value)
        self.usar_camara = bool(self.get_parameter('usar_camara').value)
        self.usar_zonas = bool(self.get_parameter('usar_zonas').value)
        self.espera_deteccion = float(self.get_parameter('espera_deteccion_s').value)
        self.timeout_goal = float(self.get_parameter('timeout_goal_s').value)
        self.archivo_rechazos = str(self.get_parameter('archivo_rechazos').value)
        self.archivo_intentos = str(self.get_parameter('archivo_intentos').value)
        self.gripper_habilitada = bool(self.get_parameter('gripper_habilitada').value)
        self.gripper_timeout = float(self.get_parameter('gripper_timeout_s').value)

        self._preparar_csv()

        grupo = ReentrantCallbackGroup()
        self.cli_mover = ActionClient(self, MoveArm, 'move_arm', callback_group=grupo)
        self.pinza = Pinza(
            self,
            accion=str(self.get_parameter('gripper_action').value),
            abierto=float(self.get_parameter('gripper_abierto').value),
            cerrado=float(self.get_parameter('gripper_cerrado').value),
            esfuerzo=float(self.get_parameter('gripper_esfuerzo').value),
            timeout=self.gripper_timeout,
        )

        self.create_subscription(String, str(self.get_parameter('topico_decision').value),
                                 self._on_decision, 10, callback_group=grupo)
        self.create_subscription(String, str(self.get_parameter('topico_deteccion').value),
                                 self._on_deteccion, 10, callback_group=grupo)
        # Suscripción de SOLO LECTURA: captura la pose alcanzada para el error de FK
        self.create_subscription(JointState, '/joint_states', self._on_joint_states, 10,
                                 callback_group=grupo)

        self.lock = threading.Lock()
        self.q_actual = [0.0] * 6
        self.deteccion = None
        self.cola = queue.Queue()
        self._parar = threading.Event()
        self.intento = 0
        self.cargando = False

        self.hilo = threading.Thread(target=self._trabajador, daemon=True)
        self.hilo.start()

        self.get_logger().info('=' * 60)
        self.get_logger().info('  ORQUESTADOR ITEM2 LISTO')
        self.get_logger().info(f'  escala prioridad : x{self.escala}')
        self.get_logger().info(f'  paso_max_rad     : {self.paso_max}')
        self.get_logger().info(f'  usar_camara      : {self.usar_camara}')
        self.get_logger().info(f'  usar_zonas       : {self.usar_zonas}'
                               f'{"" if self.usar_zonas else "  [pose unica legacy]"}')
        self.get_logger().info(f'  pinza (acción)   : {self.get_parameter("gripper_action").value}'
                               f'{" [SIMULADA]" if not self.gripper_habilitada else ""}')
        self.get_logger().info('=' * 60)

    # 1. Utilidades de CSV y espera
    def _preparar_csv(self):
        intentos_mod.preparar_csv(self.archivo_intentos)
        if not os.path.exists(self.archivo_rechazos):
            with open(self.archivo_rechazos, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(['t_unix', 'client_id', 'priority', 'causa', 'motivo', 'frase'])

    @staticmethod
    def _esperar(futuro, timeout):
        evento = threading.Event()
        futuro.add_done_callback(lambda _: evento.set())
        if not evento.wait(timeout):
            return None
        return futuro.result()

    # 2. Callbacks de suscripción
    def _on_joint_states(self, msg):
        with self.lock:
            if len(msg.position) >= 6:
                # /joint_states llega en GRADOS (broker lo publica así para el driver del kit)
                self.q_actual = [float(math.radians(v)) for v in msg.position[:6]]

    def _on_deteccion(self, msg):
        try:
            datos = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        with self.lock:
            self.deteccion = datos

    def _on_decision(self, msg):
        try:
            self.cola.put(json.loads(msg.data))
        except json.JSONDecodeError:
            self.get_logger().error(f'decisión inválida: {msg.data!r}')

    # 3. Hilo trabajador: procesa una orden completa a la vez
    def _trabajador(self):
        while not self._parar.is_set():
            try:
                decision = self.cola.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._atender(decision)
            except Exception as e:
                self.get_logger().error(f'error atendiendo la orden: {e!r}')

    def _rechazar(self, decision, causa, motivo):
        with open(self.archivo_rechazos, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                f'{time.time():.3f}', self.client_id, int(decision.get('prioridad', 0)),
                causa, motivo, decision.get('frase', ''),
            ])
        self.get_logger().warn(
            f'⛔ RECHAZADA ({causa}) sin encolar: "{decision.get("frase", "")}" — {motivo}')

    # 4. Espera de la confirmación visual del color
    def _esperar_deteccion(self, color):
        limite = time.time() + self.espera_deteccion
        while time.time() < limite and rclpy.ok():
            with self.lock:
                det = dict(self.deteccion) if self.deteccion else None
            if det and det.get('presente') and det.get('color') == color and det.get('estable'):
                return det
            time.sleep(0.05)
        return None

    def _mapa_slots(self):
        """Devuelve {slot:int -> color:str} de la última detección, o {} si no hay nada."""
        with self.lock:
            det = dict(self.deteccion) if self.deteccion else None
        if not det:
            return {}
        por_slot = det.get('por_slot') or {}
        mapa = {}
        for s, c in por_slot.items():
            try:
                mapa[int(s)] = c
            except (TypeError, ValueError):
                continue
        return mapa

    def _esperar_slot(self, color):
        """Espera a que el MAPA estable {slot: color} contenga `color` y devuelve el slot (1..4).

        Devuelve None si en `espera_deteccion_s` no apareció ese color en ninguna posición."""
        limite = time.time() + self.espera_deteccion
        while time.time() < limite and rclpy.ok():
            with self.lock:
                det = dict(self.deteccion) if self.deteccion else None
            if det and det.get('estable'):
                for s, c in (det.get('por_slot') or {}).items():
                    if c == color:
                        try:
                            return int(s)
                        except (TypeError, ValueError):
                            continue
            time.sleep(0.05)
        return None

    # 5. Envío de un movimiento al broker (una meta, ya troceada por escalonar)
    def _enviar_pose(self, q_rad, prioridad):
        if not self.cli_mover.wait_for_server(timeout_sec=self.timeout_goal):
            self.get_logger().error('el broker no aparece (¿corre arm_broker?)')
            return False
        goal = MoveArm.Goal()
        goal.joint_positions = [float(v) for v in q_rad]
        goal.client_id = self.client_id
        goal.priority = prioridad
        handle = self._esperar(self.cli_mover.send_goal_async(goal, feedback_callback=self._feedback),
                               self.timeout_goal)
        if handle is None or not handle.accepted:
            self.get_logger().warn('el broker RECHAZÓ el goal (ver rechazos.csv del broker)')
            return False
        resultado = self._esperar(handle.get_result_async(), self.timeout_goal)
        if resultado is None:
            self.get_logger().warn('sin resultado del broker (timeout)')
            return False
        r = resultado.result
        self.get_logger().info(
            f'   🦾 success={r.success} espera={r.wait_time_s:.2f}s ejec={r.exec_time_s:.2f}s')
        return bool(r.success)

    def _mover_a(self, grados, prioridad):
        """Mueve hacia la pose destino (en grados), troceando en metas que respeten paso_max"""
        destino = poses_mod.a_radianes(grados)
        exito = True
        with self.lock:
            origen = list(self.q_actual)
        for meta in poses_mod.escalonar(origen, destino, self.paso_max):
            if not self._enviar_pose(meta, prioridad):
                exito = False
                break
            with self.lock:
                origen = list(self.q_actual)
        return exito, destino

    def _feedback(self, msg):
        f = msg.feedback
        self.get_logger().info(
            f'   {f.state} pos={f.queue_position} t={f.elapsed_s:.1f}s',
            throttle_duration_sec=1.0)

    # 6. Atención de una decisión válida (despacho por acción: agarrar / soltar / mover)
    def _atender(self, decision):
        frase = decision.get('frase', '')
        accion = (decision.get('accion') or 'desconocido').lower()
        if accion == 'llevar':
            accion = 'mover'
        objeto = decision.get('objeto', 'desconocido')
        color = (decision.get('color') or 'ninguno').lower()
        motivo = decision.get('motivo', '')

        if not decision.get('permitido', False):
            self._rechazar(decision, 'no_permitida', motivo or 'el modelo marcó permitido=False')
            return

        # 'detener' no necesita objeto/color: limpia la cola y vuelve a HOME
        if accion == 'detener':
            self._detener(decision)
            return

        tiene_color = color not in ('', 'ninguno')
        # Sin relleno: una acción que no está en la lista NO se convierte en 'mover'. Si no se
        # reconoce la acción, la orden se rechaza (antes se ejecutaba igual como traslado y eso
        # contradecía lo que el log mostraba como 'desconocido')
        if accion not in ('agarrar', 'soltar', 'mover'):
            self._rechazar(decision, 'accion_desconocida',
                           f'la acción {accion!r} no se reconoce; no hay nada que ejecutar')
            return
        if accion != 'soltar' and (objeto == 'desconocido' or not tiene_color):
            self._rechazar(decision, 'objeto_desconocido',
                           'objeto o color no reconocidos; no hay pose de agarre')
            return

        prioridad = max(0, min(255, int(decision.get('prioridad', 0)) * self.escala))

        # 'soltar': abre donde esté, sin tocar la cola de búsqueda/cámara.
        if accion == 'soltar':
            self.intento += 1
            self.get_logger().info(f'▶️  intento {self.intento}: "{frase}" accion=soltar')
            self._ejecutar_accion(decision, poses_mod.plan_soltar(), prioridad,
                                  medir_recogida=False, cargando=False, zona='soltar')
            return

        # 'mover' cuando YA hay un cubo en mano (self.cargando, de una 'agarrar' anterior):
        # no hay que volver a buscar/agarrar, solo falta completar el tramo de transporte.
        continuar_cargado = (accion == 'mover' and self.cargando)

        slot = None
        if not continuar_cargado:
            # 'agarrar' y 'mover' desde cero necesitan ir a POSE_BUSQUEDA y que la cámara
            # confirme el color ANTES de moverse más: si no, se vería la mesa desde otra
            # pose y nunca confirmaría nada.
            self.get_logger().info('🔎 yendo a POSE_BUSQUEDA (espacio de detección)')
            llego, _ = self._mover_a(poses_mod.POSE_BUSQUEDA, prioridad)
            if not llego:
                # Antes este resultado se ignoraba: si el broker rechazaba este goal (p.ej.
                # paso_max_rad distinto al del broker) el código seguía de largo como si el
                # brazo ya estuviera en posición. Revisa rechazos.csv del BROKER (no este CSV).
                self._rechazar(decision, 'fallo_movimiento',
                               'no se pudo llegar a POSE_BUSQUEDA (revisa rechazos.csv del '
                               'broker y que arm_broker esté corriendo)')
                return
            if self.usar_camara and self.usar_zonas:
                # Con 4 posiciones: la cámara publica el mapa {slot: color}; aquí se resuelve
                # EN QUÉ posición está el color pedido. Si no está en ninguna, se rechaza.
                slot = self._esperar_slot(color)
                if slot is None:
                    self._rechazar(decision, 'color_no_encontrado',
                                   f'la cámara no vio el color {color} en ninguna de las 4 '
                                   f'posiciones (mapa={self._mapa_slots()})')
                    return
                self.get_logger().info(f'📍 color {color} detectado en slot {slot} '
                                       f'(mapa={self._mapa_slots()})')
            elif self.usar_camara:
                det = self._esperar_deteccion(color)
                if det is None:
                    self._rechazar(decision, 'sin_deteccion',
                                   f'la cámara no confirmó un objeto {color} estable sobre la mesa')
                    return

        self.intento += 1
        self.get_logger().info(
            f'▶️  intento {self.intento}: "{frase}" accion={accion} '
            f'({objeto}/{color}) priority={prioridad} cargando={self.cargando} '
            f'slot={slot}')

        zona = f'slot{slot}_{color}' if slot else f'zona_{color}'
        if accion == 'agarrar':
            self._ejecutar_accion(decision, poses_mod.plan_agarrar(slot), prioridad,
                                  medir_recogida=True, cargando=True,
                                  recogida_grados=poses_mod.recogida(slot), zona=zona)
        elif continuar_cargado:
            # Ya tiene el cubo en POSE_BUSQUEDA: solo falta reparto→destino[color]→abrir→home
            self._ejecutar_accion(decision, poses_mod.plan_transportar(color), prioridad,
                                  medir_recogida=False, cargando=False,
                                  zona=f'transporte_{color}')
        else:
            # 'mover' de cero: pick-and-place completo (agarre en su slot + transporte + home)
            self._ejecutar_accion(decision, poses_mod.plan_pick_and_place(color, slot), prioridad,
                                  medir_recogida=True, cargando=False,
                                  recogida_grados=poses_mod.recogida(slot), zona=zona)

    def _ejecutar_accion(self, decision, pasos, prioridad, medir_recogida, cargando,
                         recogida_grados=None, zona=None):
        """Ejecuta una secuencia de pasos, registra el intento y actualiza el estado de carga

        `recogida_grados` es la pose de agarre realmente pedida (la del slot); si es None se mide
        contra POSE_RECOGIDA (legacy). `zona` es la etiqueta para intentos.csv (p.ej. slot3_verde)."""
        q_recogida_pedida = poses_mod.a_radianes(recogida_grados or poses_mod.POSE_RECOGIDA)
        q_recogida_alcanzada = list(q_recogida_pedida)
        exito = True

        for paso in pasos:
            if paso[0] == 'gripper':
                if self.gripper_habilitada:
                    ok = self.pinza.abrir() if paso[1] == 'abrir' else self.pinza.cerrar()
                else:
                    self.get_logger().warn(
                        f'🖐  pinza SIMULADA ({paso[1]}): gripper_habilitada=false', throttle_duration_sec=2.0)
                    ok = True
                exito = exito and ok
            else:
                ok, destino = self._mover_a(paso[2], prioridad)
                exito = exito and ok
                if paso[1] == 'recogida':
                    with self.lock:
                        q_recogida_alcanzada = list(self.q_actual)

        self.cargando = cargando
        frase = decision.get('frase', '')
        objeto = decision.get('objeto', 'desconocido')
        color = (decision.get('color') or 'ninguno').lower()
        error = (intentos_mod.error_mm(q_recogida_pedida, q_recogida_alcanzada)
                 if medir_recogida else 0.0)
        intentos_mod.registrar(self.archivo_intentos, self.intento, frase, objeto, color,
                               zona or f'zona_{color}', exito, q_recogida_pedida,
                               q_recogida_alcanzada, error)
        self.get_logger().info(
            f'🏁 intento {self.intento}: exito={exito} error_FK={error:.2f} mm '
            f'(cargando={self.cargando})')

    def _detener(self, decision):
        """Limpia la cola de órdenes pendientes y regresa el brazo a HOME"""
        vaciados = 0
        while True:
            try:
                self.cola.get_nowait()
                vaciados += 1
            except queue.Empty:
                break
        self.get_logger().info(
            f'⏹️  DETENER: cola limpiada ({vaciados} órdenes descartadas); vuelvo a HOME')
        self._mover_a(poses_mod.POSE_HOME, 0)
        self.cargando = False

    # 7. Cierre
    def destroy_node(self):
        self._parar.set()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    nodo = OrquestadorItem2()
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
