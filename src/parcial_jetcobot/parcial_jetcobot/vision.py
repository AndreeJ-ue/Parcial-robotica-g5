"""Mapa color→P1–P4 por regiones (ROI) de la imagen tomada en la postura de búsqueda."""
import time
import threading
import numpy as np
import cv2
from .modelos import Pose, FalloTarea
from .posiciones import validar_regiones, pose_de


def mapa_posiciones(frame, config):
    validar_regiones(config)
    esperado = tuple(config['camara']['resolucion_calibracion_px'])
    if (frame.shape[1],frame.shape[0]) != esperado:
        raise FalloTarea('Resolución distinta de la imagen usada para definir las regiones')
    camara=config['camara']; mapa={}
    for nombre,p in config['manipulacion']['posiciones'].items():
        x,y,w,h=p['roi_xywh']; imagen=frame[y:y+h,x:x+w]
        hsv=cv2.cvtColor(imagen,cv2.COLOR_BGR2HSV); candidatos=[]
        for color,rangos in camara['hsv'].items():
            mascara=np.zeros((h,w),dtype=np.uint8)
            for bajo,alto in rangos:
                mascara |= cv2.inRange(hsv,np.array(bajo,dtype=np.uint8),np.array(alto,dtype=np.uint8))
            mascara=cv2.morphologyEx(mascara,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
            contornos,_=cv2.findContours(mascara,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            minimo=max(camara['area_minima_px'],w*h*camara.get('fraccion_minima_roi',.10))
            regiones=[c for c in contornos if cv2.contourArea(c)>=minimo]
            if len(regiones)>1:raise FalloTarea(nombre+': varias regiones del mismo color')
            if regiones:candidatos.append(color)
        if len(candidatos)>1:raise FalloTarea(nombre+': región de recogida ambigua')
        mapa[nombre]=candidatos[0] if candidatos else None
    return mapa


def seleccionar_posicion(mapa,decision,config):
    elegidas=[n for n,c in mapa.items() if c==decision.color]
    if not elegidas:raise FalloTarea('Color solicitado ausente en P1–P4')
    if len(elegidas)!=1:raise FalloTarea('Color solicitado duplicado en varias posiciones')
    nombre=elegidas[0];p=config['manipulacion']['posiciones'][nombre]
    if decision.objeto not in ('objeto',p['objeto']):
        raise FalloTarea('El objeto solicitado no corresponde al tipo calibrado en la posición')
    return nombre,pose_de(p),p.get('altura_aproximacion_m',0.0)


class CameraFeed:
    def __init__(self,indice,resolucion=None):
        self.lock=threading.Lock(); self.frame=None; self.recibido=0.0
        self.parar=threading.Event();self.resolucion=resolucion
        self.hilo=threading.Thread(target=self._leer,args=(indice,),daemon=True)
        self.hilo.start()
    def _leer(self,indice):
        cap=cv2.VideoCapture(indice)
        if self.resolucion:
            # Las ROI se definieron a esta resolución; mapa_posiciones rechaza otra.
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,int(self.resolucion[0]));cap.set(cv2.CAP_PROP_FRAME_HEIGHT,int(self.resolucion[1]))
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
    def posterior(self, timeout_s=2.0):
        inicio=time.monotonic();fin=inicio+timeout_s
        while time.monotonic()<fin:
            with self.lock:
                if self.frame is not None and self.recibido>inicio:
                    return self.frame.copy()
            if self.parar.wait(.01):break
        raise FalloTarea('No llegó una imagen nueva después de solicitar percepción')
    def cerrar(self):
        self.parar.set(); self.hilo.join(timeout=1)
