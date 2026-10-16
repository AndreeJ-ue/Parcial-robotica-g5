"""Cadena llamada únicamente por el worker heredado del RB2."""
import math
import time
from dataclasses import dataclass, field
from .modelos import Pose, FalloTarea, Cancelado
from .posiciones import usa_posiciones, usa_articular, validar, pose_de, destino_para, comprobar_busqueda, q_rad_de


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
    posicion_id: str = ''
    mapa_colores: dict = field(default_factory=dict)
    destino: str = ''
    error_fk_recogida_mm: float = -1.0


def ejecutar(decision, backend, config, cancelado=lambda:False, feedback=lambda _:None):
    if usa_articular(config):
        return ejecutar_articular(decision,backend,config,cancelado,feedback)
    if usa_posiciones(config):
        return ejecutar_fijas(decision,backend,config,cancelado,feedback)
    return ResultadoTarea(simulado=backend.simulado,
                          motivo='Estrategia de manipulación no soportada: usar manipulacion.estrategia=posiciones_fijas')


def ejecutar_articular(decision,backend,config,cancelado,feedback):
    """P1–P4 con poses articulares enseñadas: búsqueda → cámara → agarre → subida → depósito → búsqueda.

    Solo se ejecuta desde el worker del broker; la pinza también se acciona desde aquí.
    """
    from .vision import seleccionar_posicion
    from .articular import error_fk_mm
    r=ResultadoTarea(simulado=backend.simulado);comienzo=time.perf_counter()
    def comprobar():
        if cancelado():raise Cancelado('Pedido cancelado; comprobar estado físico antes de recuperar')
    def etapa(nombre,funcion):
        comprobar();feedback(nombre);inicio=time.perf_counter()
        try:return funcion()
        finally:r.etapas_s[nombre]=r.etapas_s.get(nombre,0)+(time.perf_counter()-inicio)
    def movimiento(plan,etiqueta='movimiento'):
        if r.inicio_comando_wall_ns==0:
            r.preparacion_s=time.perf_counter()-comienzo
            r.gripper_previo_s=r.etapas_s.get('gripper',0)
            r.inicio_comando_wall_ns=time.time_ns()
        etapa(etiqueta,lambda:backend.ejecutar(plan,cancelado))
    try:
        decision.validar()
        if not decision.permitido:raise FalloTarea('Orden no permitida')
        validar(config,real=not backend.simulado)
        r.destino=destino_para(decision,config)
        b=config['manipulacion']['busqueda'];q_b=list(b['q_rad']);q_actual=backend.estado()
        if max(abs(a-c) for a,c in zip(q_actual,q_b))>b['tolerancia_rad']:
            plan=etapa('planificacion_busqueda',lambda:backend.planificar(q_actual,q_b))
            movimiento(plan,'busqueda')
        etapa('estabilizacion_busqueda',lambda:backend.esperar_busqueda(cancelado))
        comprobar_busqueda(backend.estado(),config)
        etapa('percepcion',lambda:backend.localizar(decision))
        comprobar_busqueda(backend.estado(),config)
        r.posicion_id=backend.posicion_id;r.mapa_colores=dict(backend.mapa_colores)
        seleccion,_,_=seleccionar_posicion(r.mapa_colores,decision,config)
        if seleccion!=r.posicion_id:raise FalloTarea('Posición seleccionada distinta del mapa de colores')
        posicion=config['manipulacion']['posiciones'][r.posicion_id];zona=config['zonas'][r.destino]
        # IK precalculada: solución articular enseñada para la posición y el depósito.
        q_rec,q_dep=etapa('cinematica_inversa',lambda:(q_rad_de(posicion,r.posicion_id),q_rad_de(zona,r.destino)))
        tramos=[('bajar',q_b,q_rec),('subir',q_rec,q_b),('depositar',q_b,q_dep)]
        planes=[etapa('planificacion',lambda a=a,c=c:backend.planificar(a,c)) for _,a,c in tramos]
        retorno=etapa('planificacion_retorno',lambda:backend.planificar(q_dep,q_b))
        etapa('gripper',lambda:backend.pinza(True,cancelado))
        movimiento(planes[0])
        if not backend.simulado:r.error_fk_recogida_mm=error_fk_mm(backend.estado(),q_rec)
        etapa('gripper',lambda:backend.pinza(False,cancelado))
        movimiento(planes[1]);movimiento(planes[2])
        r.q_medida_rad=list(backend.estado());r.solicitado_xyz_m=list(pose_de(zona).xyz_m)
        if not backend.simulado:r.error_fk_mm=error_fk_mm(r.q_medida_rad,q_dep)
        etapa('gripper',lambda:backend.pinza(True,cancelado))
        movimiento(retorno,'retorno')
        etapa('estabilizacion_retorno',lambda:backend.esperar_busqueda(cancelado))
        comprobar_busqueda(backend.estado(),config)
        r.exito=True
        r.motivo=('Secuencia articular simulada; no acredita agarre físico' if backend.simulado else
                  'Secuencia articular completada y retorno a búsqueda confirmado; verificar objeto y depósito físicamente')
    except (FalloTarea,ValueError,RuntimeError) as exc:r.motivo=str(exc)
    finally:
        r.inicio_movimiento_wall_ns=getattr(backend,'inicio_movimiento_wall_ns',0)
        r.inicio_comando_wall_ns=getattr(backend,'primer_comando_wall_ns',0) or r.inicio_comando_wall_ns
    return r


def ejecutar_fijas(decision,backend,config,cancelado,feedback):
    r=ResultadoTarea(simulado=backend.simulado);comienzo=time.perf_counter()
    def comprobar():
        if cancelado():raise Cancelado('Pedido cancelado; comprobar estado físico antes de recuperar')
    def etapa(nombre,funcion):
        comprobar();feedback(nombre);inicio=time.perf_counter()
        try:return funcion()
        finally:r.etapas_s[nombre]=r.etapas_s.get(nombre,0)+(time.perf_counter()-inicio)
    def movimiento(plan,etiqueta='movimiento'):
        primero=r.inicio_comando_wall_ns==0
        if primero:
            r.preparacion_s=time.perf_counter()-comienzo
            r.gripper_previo_s=r.etapas_s.get('gripper',0)
        inicio=time.time_ns()
        etapa(etiqueta,lambda:backend.ejecutar(plan,cancelado))
        if primero:r.inicio_comando_wall_ns=getattr(backend,'primer_comando_wall_ns',0) or inicio
    try:
        decision.validar()
        if not decision.permitido:raise FalloTarea('Orden no permitida')
        validar(config,real=not backend.simulado)
        r.destino=destino_para(decision,config)
        b=config['manipulacion']['busqueda'];q_actual=backend.estado()
        if max(abs(a-c) for a,c in zip(q_actual,b['q_rad']))>b['tolerancia_rad']:
            plan=etapa('planificacion_busqueda',lambda:backend.planificar(q_actual,b['q_rad']))
            movimiento(plan,'busqueda')
        etapa('estabilizacion_busqueda',lambda:backend.esperar_busqueda(cancelado))
        comprobar_busqueda(backend.estado(),config)
        recogida=etapa('percepcion',lambda:backend.localizar(decision)).validar()
        # Comprobar de nuevo después de capturar, por si se alteró la cámara.
        comprobar_busqueda(backend.estado(),config)
        r.posicion_id=backend.posicion_id;r.mapa_colores=dict(backend.mapa_colores)
        from .vision import seleccionar_posicion
        seleccion,_,_=seleccionar_posicion(r.mapa_colores,decision,config)
        if seleccion!=r.posicion_id:raise FalloTarea('Posición seleccionada distinta del mapa de colores')
        if r.posicion_id not in config['manipulacion']['posiciones']:
            raise FalloTarea('Percepción devolvió una posición no calibrada')
        p=config['manipulacion']['posiciones'][r.posicion_id]
        medida=pose_de(p)
        if recogida.frame_id!=medida.frame_id or math.dist(recogida.xyz_m,medida.xyz_m)>1e-6 or any(abs(a-c)>1e-6 for a,c in zip(recogida.quaternion_xyzw,medida.quaternion_xyzw)):
            raise FalloTarea('La respuesta de percepción no coincide con la pose de la posición calibrada')
        deposito=pose_de(config['zonas'][r.destino])
        if deposito.frame_id!=recogida.frame_id:raise FalloTarea('Marcos distintos de recogida y depósito')
        altura=p['altura_aproximacion_m']
        altura_deposito=config['zonas'][r.destino].get('altura_aproximacion_m',altura)
        def arriba(pose,h):return Pose([pose.xyz_m[0],pose.xyz_m[1],pose.xyz_m[2]+h],pose.quaternion_xyzw,pose.frame_id)
        poses=[arriba(recogida,altura),recogida,arriba(recogida,altura),
               arriba(deposito,altura_deposito),deposito,arriba(deposito,altura_deposito)]
        planes=[];semilla=backend.estado()
        for indice,pose in enumerate(poses):
            referencia=(p.get('semilla_ik_rad') if indice==1 else
                        config['zonas'][r.destino].get('semilla_ik_rad') if indice==4 else None)
            semilla_ik=list(referencia) if referencia is not None else semilla
            q=etapa('cinematica_inversa',lambda p=pose,s=semilla_ik:backend.ik(p,s))
            planes.append(etapa('planificacion',lambda q=q,s=semilla:backend.planificar(s,q)))
            semilla=q
        # Confirmar también que existe un plan de retorno antes de cerrar la pinza.
        retorno=etapa('planificacion_retorno',lambda:backend.planificar(semilla,b['q_rad']))
        etapa('gripper',lambda:backend.pinza(True,cancelado))
        for indice,plan in enumerate(planes):
            movimiento(plan)
            if indice==1:etapa('gripper',lambda:backend.pinza(False,cancelado))
            if indice==4:
                from arm_broker.fk import fk
                r.q_medida_rad=list(backend.estado());r.solicitado_xyz_m=list(deposito.xyz_m)
                if not backend.simulado:r.error_fk_mm=math.dist(fk(r.q_medida_rad),[v*1000 for v in deposito.xyz_m])
                etapa('gripper',lambda:backend.pinza(True,cancelado))
        movimiento(retorno,'retorno')
        etapa('estabilizacion_retorno',lambda:backend.esperar_busqueda(cancelado))
        comprobar_busqueda(backend.estado(),config)
        r.exito=True
        r.motivo=('Secuencia P1–P4 simulada; no acredita agarre físico' if backend.simulado else
                  'Secuencia completada y retorno a búsqueda confirmado; verificar objeto y depósito físicamente')
    except (FalloTarea,ValueError,RuntimeError) as exc:r.motivo=str(exc)
    finally:
        r.inicio_movimiento_wall_ns=getattr(backend,'inicio_movimiento_wall_ns',0)
        r.inicio_comando_wall_ns=getattr(backend,'primer_comando_wall_ns',0) or r.inicio_comando_wall_ns
    return r


class BackendSimulado:
    simulado = True
    def __init__(self,config):
        self.config = config
        self.q = [0.0]*6
        self.inicio_movimiento_wall_ns = 0
        self.operaciones = []
        self.posicion_id='';self.mapa_colores={};self.primer_comando_wall_ns=0
    def estado(self): return list(self.q)
    def localizar(self,d):
        from .vision import seleccionar_posicion
        self.mapa_colores=dict(self.config['manipulacion']['mapa_simulado'])
        self.posicion_id,pose,_=seleccionar_posicion(self.mapa_colores,d,self.config)
        return pose
    def ik(self,pose,semilla):
        # Es un doble de IK, no un solver ni una postura válida para el hardware.
        pose.validar()
        return [pose.xyz_m[0],pose.xyz_m[1],pose.xyz_m[2],0.0,0.0,0.0]
    def planificar(self,inicio,final): return [list(inicio),list(final)]
    def ejecutar(self,plan,cancelado):
        if cancelado(): raise Cancelado('Cancelado')
        # Retardo opcional para que la cola del broker sea visible en la prueba simulada.
        retardo=float(self.config.get('hardware',{}).get('retardo_simulado_s',0.0))
        fin=time.monotonic()+retardo
        while time.monotonic()<fin:
            if cancelado(): raise Cancelado('Cancelado')
            time.sleep(0.02)
        self.q = list(plan[-1]); self.operaciones.append('movimiento')
    def esperar_busqueda(self,cancelado):
        if cancelado():raise Cancelado('Cancelado')
        comprobar_busqueda(self.estado(),self.config)
    def pinza(self,abierta,cancelado):
        if cancelado(): raise Cancelado('Cancelado')
        self.operaciones.append('abrir' if abierta else 'cerrar')
