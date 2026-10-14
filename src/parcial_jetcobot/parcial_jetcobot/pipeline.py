"""Cadena llamada únicamente por el worker heredado del RB2."""
import math
import time
from dataclasses import dataclass, field
from .modelos import Pose, FalloTarea, Cancelado


@dataclass
class ResultadoTarea:
    exito: bool = False
    simulado: bool = True
    motivo: str = ''
    etapas_s: dict = field(default_factory=dict)
    error_fk_mm: float = -1.0
    inicio_comando_wall_ns: int = 0
    inicio_movimiento_wall_ns: int = 0
    q_medida_rad: list = field(default_factory=list)
    solicitado_xyz_m: list = field(default_factory=list)
    preparacion_s: float = 0.0
    gripper_previo_s: float = 0.0


def ejecutar(decision, backend, config, cancelado=lambda:False, feedback=lambda _:None):
    resultado = ResultadoTarea(simulado=backend.simulado)
    comienzo = time.perf_counter()
    def comprobar():
        if cancelado(): raise Cancelado('Pedido cancelado; comprobar parada física si estaba en movimiento')
    def etapa(nombre, funcion):
        comprobar()
        feedback(nombre)
        t0 = time.perf_counter()
        try:
            return funcion()
        finally:
            resultado.etapas_s[nombre] = resultado.etapas_s.get(nombre,0)+(time.perf_counter()-t0)
    try:
        decision.validar()
        if not decision.permitido:
            raise FalloTarea('Orden no permitida')
        if decision.destino not in config['zonas']:
            raise FalloTarea('Zona desconocida')
        recogida = etapa('percepcion', lambda: backend.localizar(decision)).validar()
        zona = config['zonas'][decision.destino]
        if not zona.get('confirmada') and not backend.simulado:
            raise FalloTarea('Zona de depósito no calibrada')
        deposito = Pose(zona['xyz_m'], zona['quaternion_xyzw'], zona['frame_id']).validar()
        if recogida.frame_id != deposito.frame_id:
            raise FalloTarea('Marcos distintos; falta transformación')
        altura = config['agarre']['altura_aproximacion_m']
        arriba = lambda p: Pose([p.xyz_m[0], p.xyz_m[1], p.xyz_m[2]+altura],p.quaternion_xyzw,p.frame_id)
        poses = [arriba(recogida), recogida, arriba(recogida), arriba(deposito), deposito, arriba(deposito)]
        trayectoria = []
        semilla = backend.estado()
        # Planificar todo antes de empezar: un fallo no deja el objeto agarrado por sorpresa.
        for pose in poses:
            q = etapa('cinematica_inversa', lambda p=pose,s=semilla: backend.ik(p,s))
            trayectoria.append(etapa('planificacion', lambda q=q,s=semilla: backend.planificar(s,q)))
            semilla = q
        comprobar()
        etapa('gripper', lambda: backend.pinza(True, cancelado))
        for indice, plan in enumerate(trayectoria):
            comprobar()
            def mover(plan=plan):
                if resultado.inicio_comando_wall_ns == 0:
                    resultado.inicio_comando_wall_ns = time.time_ns()
                    resultado.preparacion_s = time.perf_counter()-comienzo
                    resultado.gripper_previo_s = resultado.etapas_s.get('gripper',0.0)
                backend.ejecutar(plan,cancelado)
            etapa('movimiento',mover)
            if indice == 1: etapa('gripper',lambda:backend.pinza(False,cancelado))
            if indice == 4:
                resultado.solicitado_xyz_m = list(deposito.xyz_m)
                q_medida = backend.estado()
                resultado.q_medida_rad = list(q_medida)
                # Solo el backend real devuelve ángulos confirmados; simulación se marca.
                from arm_broker.fk import fk
                alcanzada = fk(q_medida)
                if not backend.simulado:
                    resultado.error_fk_mm = math.dist(alcanzada,[v*1000 for v in deposito.xyz_m])
                etapa('gripper',lambda:backend.pinza(True,cancelado))
        resultado.inicio_movimiento_wall_ns = backend.inicio_movimiento_wall_ns
        resultado.exito = True
        resultado.motivo = ('Cadena simulada; no acredita agarre físico' if backend.simulado
                            else 'Secuencia ejecutada; verificar objeto y zona para calificar éxito del intento')
    except (FalloTarea, ValueError, RuntimeError) as exc:
        resultado.motivo = str(exc)
    return resultado


class BackendSimulado:
    simulado = True
    def __init__(self,config):
        self.config = config
        self.q = [0.0]*6
        self.inicio_movimiento_wall_ns = 0
        self.operaciones = []
    def estado(self): return list(self.q)
    def localizar(self,d):
        objeto = next((x for x in self.config['catalogo']
                       if x['color']==d.color and (d.objeto=='objeto' or x['objeto']==d.objeto)),None)
        if objeto is None: raise FalloTarea('Objeto solicitado ausente')
        return Pose(objeto['xyz_simulada_m'],[0,0,0,1],self.config['hardware']['frame_base'])
    def ik(self,pose,semilla):
        # Es un doble de IK, no un solver ni una postura válida para el hardware.
        pose.validar()
        return [pose.xyz_m[0],pose.xyz_m[1],pose.xyz_m[2],0.0,0.0,0.0]
    def planificar(self,inicio,final): return [list(inicio),list(final)]
    def ejecutar(self,plan,cancelado):
        if cancelado(): raise Cancelado('Cancelado')
        self.q = list(plan[-1]); self.operaciones.append('movimiento')
    def pinza(self,abierta,cancelado):
        if cancelado(): raise Cancelado('Cancelado')
        self.operaciones.append('abrir' if abierta else 'cerrar')
