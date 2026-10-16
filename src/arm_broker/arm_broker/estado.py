"""Estado de admisión independiente de ROS; el broker comparte este mismo lock."""
import math
import threading
import time


class EstadoAdmision:
    def __init__(self, capacidad, paso_max, q_inicial=None, edad_max=2.0):
        if capacidad < 1 or not math.isfinite(paso_max) or paso_max <= 0:
            raise ValueError('cola_max y paso_max_rad deben ser positivos')
        if not math.isfinite(edad_max) or edad_max <= 0:
            raise ValueError('edad_max_estado_s debe ser positivo')
        self.lock = threading.RLock()
        self.capacidad = capacidad
        self.paso_max = paso_max
        self.edad_max = edad_max
        self.q_ordenada = list(q_inicial) if q_inicial is not None else None
        self.q_medida = None
        self.t_medida = None
        self.reservados = 0  # aceptados pendientes de encolar + encolados

    def medir(self, q):
        with self.lock:
            self.q_medida = list(q)
            self.t_medida = time.monotonic()

    def referencia(self):
        with self.lock:
            if self.q_medida is not None:
                if time.monotonic() - self.t_medida > self.edad_max:
                    return None, 'estado medido obsoleto'
                return list(self.q_medida), 'medida'
            if self.q_ordenada is not None:
                return list(self.q_ordenada), 'ordenada; no confirma posición física'
            return None, 'postura inicial desconocida'

    def validar_paso(self, q):
        with self.lock:
            ref, origen = self.referencia()
            if ref is None:
                return False, origen
            paso = max(abs(b - a) for a, b in zip(ref, q))
            if paso > self.paso_max:
                return False, f'paso {paso:.3f} rad > máximo {self.paso_max:.3f} rad'
            return True, origen

    def reservar(self, q):
        with self.lock:
            ok, motivo = self.validar_paso(q)
            if not ok:
                return False, motivo
            if self.reservados >= self.capacidad:
                return False, f'cola llena: {self.reservados}/{self.capacidad}'
            self.reservados += 1
            return True, ''

    def liberar(self):
        with self.lock:
            if self.reservados <= 0:
                raise RuntimeError('liberación sin reserva')
            self.reservados -= 1

    def ordenar(self, q):
        with self.lock:
            self.q_ordenada = list(q)
