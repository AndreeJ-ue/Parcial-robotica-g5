"""Geometría medida por posición; el color se obtiene de la imagen actual."""
import math
from .modelos import Pose, FalloTarea


def usa_posiciones(config):
    return config.get('manipulacion', {}).get('estrategia') == 'posiciones_fijas'


def usa_articular(config):
    """Ejecución por poses articulares enseñadas (sin MoveIt). 'moveit' es la alternativa."""
    return usa_posiciones(config) and config['manipulacion'].get('ejecucion', 'moveit') == 'articular'


def q_rad_de(datos, nombre):
    """Seis ángulos enseñados (q_grados) convertidos a radianes, dentro de los límites del RB2."""
    from arm_broker.fk import dentro_de_limites
    q = datos.get('q_grados') if isinstance(datos, dict) else None
    if not isinstance(q, list) or len(q) != 6 or any(type(v) not in (int, float) or not math.isfinite(v) for v in q):
        raise FalloTarea(nombre + ': faltan los seis ángulos enseñados q_grados')
    rad = [math.radians(v) for v in q]
    ok, motivo = dentro_de_limites(rad)
    if not ok:
        raise FalloTarea(nombre + ': ' + motivo)
    return rad


def destinos_validos(config):
    nombres = list(config['zonas'])
    if usa_posiciones(config) and config['manipulacion'].get('destinos_por_color'):
        nombres.append('por_color')
    return nombres


def destino_para(decision, config):
    nombre = decision.destino
    if nombre == 'por_color' and usa_posiciones(config):
        nombre = config['manipulacion'].get('destinos_por_color', {}).get(decision.color)
    if nombre not in config['zonas']:
        raise FalloTarea('Destino desconocido o sin correspondencia para el color solicitado')
    return nombre


def pose_de(datos):
    if isinstance(datos, dict) and datos.get('xyz_m') is None and datos.get('q_grados') is not None:
        # Modo articular: la posición informada es la FK del RB2 de la pose enseñada.
        from arm_broker.fk import fk
        x, y, z = fk(q_rad_de(datos, 'pose'))
        return Pose([x/1000, y/1000, z/1000], [0.0, 0.0, 0.0, 1.0], datos.get('frame_id', 'base')).validar()
    try:return Pose(list(datos['xyz_m']), list(datos['quaternion_xyzw']), datos['frame_id']).validar()
    except (KeyError,TypeError,ValueError) as exc:raise FalloTarea('Falta una pose cartesiana medida válida') from exc


def validar_regiones(config):
    """Permite calibrar visión antes de completar coordenadas de movimiento."""
    try:
        puntos=config['manipulacion']['posiciones']
        if set(puntos)!={'P1','P2','P3','P4'}:raise ValueError('Se requieren exactamente P1–P4')
        ancho,alto=config['camara']['resolucion_calibracion_px']
        if type(ancho) is not int or type(alto) is not int or min(ancho,alto)<=0:
            raise ValueError('Resolución de calibración inválida')
        rois=[]
        for nombre,p in puntos.items():
            roi=p['roi_xywh']
            if not isinstance(roi,list) or len(roi)!=4 or any(type(v) is not int for v in roi):
                raise ValueError(nombre+': falta ROI [x,y,ancho,alto]')
            x,y,w,h=roi
            if min(x,y)<0 or min(w,h)<=0 or x+w>ancho or y+h>alto:raise ValueError(nombre+': ROI fuera de imagen')
            for a,b,c,d in rois:
                if max(x,a)<min(x+w,a+c) and max(y,b)<min(y+h,b+d):raise ValueError('Las regiones no deben solaparse')
            rois.append(roi)
        fraccion=config['camara'].get('fraccion_minima_roi',.10)
        area=config['camara']['area_minima_px']
        if not math.isfinite(fraccion) or not 0<fraccion<=1 or not math.isfinite(area) or area<=0:
            raise ValueError('Umbrales de región inválidos')
        rangos=config['camara']['hsv']
        if not rangos:raise ValueError('Faltan rangos HSV')
        for color,bandas in rangos.items():
            if not bandas:raise ValueError('Falta rango HSV para '+color)
            for bajo,alto_hsv in bandas:
                if len(bajo)!=3 or len(alto_hsv)!=3:raise ValueError('Rango HSV incompleto')
                for i,(a,b) in enumerate(zip(bajo,alto_hsv)):
                    if type(a) is not int or type(b) is not int or not 0<=a<=b<=(179 if i==0 else 255):
                        raise ValueError('Rango HSV inválido')
        return config
    except (KeyError,TypeError,ValueError) as exc:raise FalloTarea('Regiones no calibradas: '+str(exc)) from exc


def validar_articular(config, real=False):
    """Modo articular: ROI, búsqueda, P1–P4 y depósitos como seis ángulos enseñados."""
    try:
        validar_regiones(config)
        m = config['manipulacion']; b = m['busqueda']
        q = b['q_rad']
        if not isinstance(q, list) or len(q) != 6 or not all(type(v) in (int,float) and math.isfinite(v) for v in q):
            raise ValueError('Faltan los seis ángulos de búsqueda en radianes')
        for k in ('tolerancia_rad', 'timeout_llegada_s'):
            if not math.isfinite(b[k]) or b[k] <= 0:raise ValueError('Tolerancia/plazo de búsqueda inválidos')
        h = config['hardware']
        for k in ('velocidad_articular_rad_s', 'paso_plan_rad'):
            if type(h.get(k)) not in (int, float) or not math.isfinite(h[k]) or h[k] <= 0:
                raise ValueError('hardware.'+k+' debe ser positivo')
        for nombre, p in m['posiciones'].items():
            q_rad_de(p, nombre)
            if real and not p.get('confirmada'):raise ValueError(nombre+': posición/ROI no confirmados')
        for color, zona in m.get('destinos_por_color', {}).items():
            if zona not in config['zonas']:raise ValueError('Destino por color inexistente: '+color)
        for nombre, z in config['zonas'].items():
            q_rad_de(z, nombre)
            if real and not z.get('confirmada'):raise ValueError(nombre+': depósito no confirmado')
        if real:
            if not b.get('confirmada'):raise ValueError('Postura de búsqueda pendiente de verificar')
            if not config['camara'].get('calibracion_confirmada'):
                raise ValueError('Regiones de cámara sin confirmar en postura de búsqueda')
        return config
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FalloTarea('Configuración articular incompleta: '+str(exc)) from exc


def validar(config, real=False):
    """No admite coordenadas/ROI pendientes ni poses ajenas al marco configurado."""
    if usa_articular(config):
        return validar_articular(config, real)
    try:
        validar_regiones(config)
        m = config['manipulacion']
        busqueda = m['busqueda']
        q = busqueda['q_rad']
        if not isinstance(q, list) or len(q) != 6 or not all(type(v) in (int,float) and math.isfinite(v) for v in q):
            raise ValueError('Faltan los seis ángulos de búsqueda en radianes')
        for k in ('tolerancia_rad', 'timeout_llegada_s'):
            if not math.isfinite(busqueda[k]) or busqueda[k] <= 0:
                raise ValueError('Tolerancia/plazo de búsqueda inválidos')
        if not math.isfinite(busqueda['asentamiento_s']) or busqueda['asentamiento_s'] < 0:
            raise ValueError('Asentamiento de búsqueda inválido')
        puntos = m['posiciones']
        if set(puntos) != {'P1','P2','P3','P4'}:
            raise ValueError('Se requieren exactamente P1, P2, P3 y P4')
        for nombre, p in puntos.items():
            pose = pose_de(p)
            if pose.frame_id != config['hardware']['frame_base']:
                raise ValueError(nombre+': frame distinto de la base configurada')
            if not math.isfinite(p['altura_aproximacion_m']) or p['altura_aproximacion_m'] <= 0:
                raise ValueError(nombre+': altura de aproximación inválida')
            semilla=p.get('semilla_ik_rad')
            if semilla is not None and (not isinstance(semilla,list) or len(semilla)!=6 or any(type(v) not in (int,float) or not math.isfinite(v) for v in semilla)):
                raise ValueError(nombre+': semilla IK debe contener seis radianes finitos')
            if real and not p.get('confirmada'):
                raise ValueError(nombre+': posición/ROI no confirmados')
        for color,zona in m.get('destinos_por_color',{}).items():
            if zona not in config['zonas']:
                raise ValueError('Destino por color inexistente: '+color)
        for nombre,z in config['zonas'].items():
            if pose_de(z).frame_id != config['hardware']['frame_base']:
                raise ValueError(nombre+': frame de depósito distinto de la base')
            if real and not z.get('confirmada'):
                raise ValueError(nombre+': depósito no confirmado')
            semilla=z.get('semilla_ik_rad')
            if semilla is not None and (not isinstance(semilla,list) or len(semilla)!=6 or any(type(v) not in (int,float) or not math.isfinite(v) for v in semilla)):
                raise ValueError(nombre+': semilla IK debe contener seis radianes finitos')
        if real:
            if not busqueda.get('confirmada') or not busqueda.get('limites_modelo_confirmados'):
                raise ValueError('Búsqueda o límites del modelo pendientes de verificar')
            if not config['camara'].get('calibracion_confirmada'):
                raise ValueError('Regiones de cámara sin confirmar en postura de búsqueda')
        return config
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FalloTarea('Configuración de posiciones fijas incompleta: '+str(exc)) from exc


def comprobar_busqueda(q, config):
    b = config['manipulacion']['busqueda']
    if len(q)!=6 or any(not math.isfinite(v) for v in q):
        raise FalloTarea('Postura medida inválida')
    if max(abs(a-bb) for a,bb in zip(q,b['q_rad'])) > b['tolerancia_rad']:
        raise FalloTarea('Cámara fuera de la postura de búsqueda calibrada')
