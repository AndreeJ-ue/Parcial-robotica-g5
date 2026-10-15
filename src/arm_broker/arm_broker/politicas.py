"""Políticas de despacho del broker: deciden qué goal sale de la cola."""

import threading
import time

class Pedido:
    """Un goal encolado, con los datos que necesitan las políticas."""

    def __init__(self, goal_handle, client_id, priority, joint_positions):
        self.goal_handle = goal_handle
        self.goal_id = bytes(goal_handle.goal_id.uuid).hex()
        self.client_id = client_id
        self.priority = int(priority)
        self.joint_positions = list(joint_positions)
        self.t_llegada = time.time()      # instante en que entró a la cola
        self.t_inicio_ejec = None         # instante en que empezó a ejecutarse
        self.fin = threading.Event()      # se libera cuando el pedido termina
        self.resultado = None             # resultado del goal, una vez ejecutado
        self.lanzado = False              # ya se mandó al brazo

    @property
    def espera_s(self):
        """Segundos que lleva esperando (hasta que arrancó, o hasta ahora)."""
        hasta = self.t_inicio_ejec if self.t_inicio_ejec else time.time()
        return hasta - self.t_llegada

    def __repr__(self):
        return f'<{self.client_id} p{self.priority} {self.goal_id}>'


# 2 política base
class Politica:
    """Interfaz común: cada política solo sabe elegir el siguiente pedido."""
    nombre = 'base'

    def siguiente(self, pendientes):
        """Devuelve el índice del pedido a atender en `pendientes`, o None si está vacía"""
        raise NotImplementedError

    def atendido(self, pedido):
        """Se avisa a la política que un pedido terminó, por si lleva cuentas"""
        pass


# 3. Política FIFO
# Es la política obligatoria: atiende en orden estricto de llegada.
# siguiente(pendientes) devuelve el ÍNDICE del pedido a atender, o None.
# Cada Pedido trae: client_id, priority, t_llegada y espera_s.
# Las políticas no modifican `pendientes`: eso lo hace el worker del broker, bajo su lock.
class FIFO(Politica):
    """Atiende primero al pedido que llegó primero, sin mirar cliente ni prioridad"""
    """Es la línea base del experimento: al ignorarla, cualquier diferencia con la segunda
    política se puede atribuir al efecto de la prioridad y no a otra cosa"""
    nombre = 'fifo'

    def siguiente(self, pendientes):
        """Entrada: pendientes = lista de Pedido
        Salida: índice del pedido con menor t_llegada, o None si no hay pedidos
        """
        if not pendientes:
            return None
        return min(range(len(pendientes)), key=lambda i: pendientes[i].t_llegada)


# 4. Política de prioridad con envejecimiento
# Es la segunda política. El enunciado ofrece tres: prioridad estática, prioridad con
# envejecimiento, o round-robin entre clientes. Se implementa el envejecimiento porque es
# la única que respeta la urgencia sin garantizar inanición (ver README.md).
class SegundaPolitica(Politica):
    """Cada pedido puntúa `priority + espera_s / tau` y sale de la cola el de mayor puntuación"""
    """El término `espera_s / tau` es el envejecimiento: la ventaja de la prioridad se desvanece
    a medida que el pedido espera, así que un goal de prioridad baja que aguanta lo suficiente
    termina saliendo por delante de uno de prioridad alta recién llegado"""
    """`tau` es la constante de tiempo del envejecimiento, en segundos, y llega desde el
    parámetro `tau_envejecimiento_s` del broker. Con tau = 12 s, un goal de prioridad 1 que
    espere 24 s iguala a uno de prioridad 3 que acaba de llegar"""
    """Efecto: la urgencia manda, pero ninguno se eterniza esperando. El precio es que la
    espera de las prioridades bajas crece; ese trade-off es justo lo que mide el ítem 3"""
    nombre = 'prioridad'

    def __init__(self, tau=8.0):
        self.tau = float(tau)
        if self.tau <= 0.0:
            raise ValueError(
                f'tau_envejecimiento_s debe ser > 0, llegó {self.tau}')
        self.atendidos = 0    # Cuántos goals salieron de la cola por esta política

    def puntuacion(self, pedido):
        """Score de un pedido: su urgencia más el peso de lo que lleva esperando"""
        return pedido.priority + pedido.espera_s / self.tau

    def siguiente(self, pendientes):
        """Entrada: pendientes = lista de Pedido
        Salida: índice del pedido con mayor puntuación, o None si no hay pedidos
        Ante empate de score sale el más antiguo: -t_llegada hace que el menor t_llegada
        gane el max, así la política nunca inventa desempates por orden de la lista
        """
        if not pendientes:
            return None

        return max(
            range(len(pendientes)),
            key=lambda i: (self.puntuacion(pendientes[i]), -pendientes[i].t_llegada))

    def atendido(self, pedido):
        """Se lleva la cuenta de goals atendidos: alimenta la traza de la corrida"""
        self.atendidos += 1

POLITICAS = {
    'fifo': FIFO,
    'prioridad': SegundaPolitica,
}
