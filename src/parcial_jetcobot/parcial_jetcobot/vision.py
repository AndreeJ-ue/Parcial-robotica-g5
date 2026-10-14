"""Detección del color solicitado; requiere homografía calibrada de cámara fija."""
import time
import threading
import numpy as np
import cv2
from .modelos import Pose, FalloTarea


def detectar(frame,color,rangos,area_min=300):
    if color not in rangos:raise FalloTarea('Color sin rango HSV configurado')
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    mascara=np.zeros(frame.shape[:2],dtype=np.uint8)
    for bajo,alto in rangos[color]:
        mascara=cv2.bitwise_or(mascara,cv2.inRange(hsv,np.array(bajo),np.array(alto)))
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
    mascara=cv2.morphologyEx(mascara,cv2.MORPH_OPEN,kernel)
    contornos,_=cv2.findContours(mascara,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    validos=[c for c in contornos if cv2.contourArea(c)>=area_min]
    if len(validos)!=1:
        raise FalloTarea('Objeto ausente o varios objetos del color solicitado')
    m=cv2.moments(validos[0])
    if not m['m00']: raise FalloTarea('Contorno inválido')
    return m['m10']/m['m00'],m['m01']/m['m00']


def pixel_a_base(pixel,homografia):
    h=np.asarray(homografia,dtype=float)
    if h.shape!=(3,3) or not np.isfinite(h).all() or abs(np.linalg.det(h))<1e-15:
        raise FalloTarea('Homografía inválida')
    p=h @ np.array([pixel[0],pixel[1],1.0])
    if abs(p[2])<1e-12: raise FalloTarea('Proyección no válida')
    return float(p[0]/p[2]),float(p[1]/p[2])


class CameraFeed:
    def __init__(self,indice):
        self.lock=threading.Lock(); self.frame=None; self.recibido=0.0
        self.parar=threading.Event()
        self.hilo=threading.Thread(target=self._leer,args=(indice,),daemon=True)
        self.hilo.start()
    def _leer(self,indice):
        cap=cv2.VideoCapture(indice)
        try:
            while not self.parar.is_set():
                ok,frame=cap.read()
                if ok:
                    with self.lock: self.frame,self.recibido=frame,time.monotonic()
                else: self.parar.wait(0.05)
        finally: cap.release()
    def actual(self):
        with self.lock:
            if self.frame is None or time.monotonic()-self.recibido>1.0:
                raise FalloTarea('No hay imagen reciente')
            return self.frame.copy()
    def cerrar(self):
        self.parar.set(); self.hilo.join(timeout=1)


def localizar(frame,d,config):
    c=config['camara']
    if not c.get('calibracion_confirmada') or not c.get('camara_fija'):
        raise FalloTarea('Calibración de cámara fija pendiente')
    obj=next((x for x in config['catalogo'] if x['color']==d.color and
              (d.objeto=='objeto' or x['objeto']==d.objeto)),None)
    if obj is None: raise FalloTarea('Objeto fuera del catálogo físico')
    if c.get('matriz_intrinseca'):
        frame=cv2.undistort(frame,np.array(c['matriz_intrinseca']),np.array(c['distorsion']))
    pixel=detectar(frame,d.color,c['hsv'],c['area_minima_px'])
    x,y=pixel_a_base(pixel,c['homografia_pixel_base_m'])
    return Pose([x,y,obj['altura_agarre_m']],config['agarre']['quaternion_xyzw'],config['hardware']['frame_base']).validar()
