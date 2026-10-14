import math
from dataclasses import dataclass, asdict


@dataclass
class Decision:
    accion: str = 'rechazar'
    objeto: str = ''
    color: str = ''
    prioridad: int = 0
    permitido: bool = False
    destino: str = 'zona_a'
    degradada: bool = False
    motivo: str = ''
    metodo: str = 'palabras_clave'
    latencia_total_ms: float = 0.0
    http_ms: float = -1.0
    calculo_servidor_ms: float = -1.0
    resto_http_ms: float = -1.0

    def validar(self):
        if self.accion not in ('recoger_depositar', 'rechazar'):
            raise ValueError('acción desconocida')
        if type(self.permitido) is not bool or type(self.degradada) is not bool:
            raise ValueError('permitido/degradada deben ser booleanos')
        if type(self.prioridad) is not int or not 0 <= self.prioridad <= 255:
            raise ValueError('prioridad fuera de 0..255')
        if self.permitido and (self.accion != 'recoger_depositar' or not self.objeto or not self.color):
            raise ValueError('decisión permitida incompleta')
        return self

    def dict(self):
        return asdict(self)


@dataclass
class Pose:
    xyz_m: list
    quaternion_xyzw: list
    frame_id: str = 'base_link'

    def validar(self):
        if len(self.xyz_m) != 3 or len(self.quaternion_xyzw) != 4:
            raise ValueError('pose incompleta')
        if not all(math.isfinite(float(x)) for x in self.xyz_m + self.quaternion_xyzw):
            raise ValueError('pose no finita')
        norma = sum(x*x for x in self.quaternion_xyzw)
        if abs(norma - 1) > 0.01:
            raise ValueError('cuaternión sin normalizar')
        if not self.frame_id:
            raise ValueError('falta frame_id')
        return self


class FalloTarea(RuntimeError):
    pass


class Cancelado(FalloTarea):
    pass
