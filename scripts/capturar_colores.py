"""Prueba visual de colores; no usa ROS, puerto serial ni movimientos."""
import argparse
from pathlib import Path
import json
import time
import cv2
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--camara',type=int,default=0)
    p.add_argument('--imagen',help='Imagen original ya guardada, como alternativa a abrir cámara')
    p.add_argument('--area-min',type=float,default=1500,help='Área mínima de una región en píxeles cuadrados')
    p.add_argument('--ancho',type=int,default=640,help='Resolución de captura; debe coincidir con resolucion_calibracion_px')
    p.add_argument('--alto',type=int,default=480)
    a=p.parse_args()
    if not np.isfinite(a.area_min) or a.area_min<=0:
        p.error('--area-min debe ser positivo')
    if a.imagen:
        frame=cv2.imread(a.imagen)
    else:
        cap=cv2.VideoCapture(a.camara)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,a.ancho);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,a.alto)
        frame=None
        try:
            for _ in range(12):
                ok,f=cap.read()
                if ok:frame=f
                time.sleep(.05)
        finally:cap.release()
    if frame is None:
        print('No se obtuvo imagen. Detén la vista previa que ocupa la cámara o usa --imagen FOTO.png.')
        return 1
    carpeta=Path('prueba_camara_'+str(time.time_ns()))
    carpeta.mkdir()
    cv2.imwrite(str(carpeta/'mesa_original.png'),frame)
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    rangos={'rojo':[((0,100,80),(10,255,255)),((170,100,80),(179,255,255))],
            'azul':[((95,80,60),(130,255,255))],
            'verde':[((35,80,60),(85,255,255))],
            'amarillo':[((20,100,80),(35,255,255))]}
    vista=frame.copy();resultados={}
    for color,intervalos in rangos.items():
        mask=np.zeros(frame.shape[:2],dtype=np.uint8)
        for bajo,alto in intervalos:
            mask=cv2.bitwise_or(mask,cv2.inRange(hsv,np.array(bajo),np.array(alto)))
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
        contornos,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        candidatos=[c for c in contornos if cv2.contourArea(c)>=a.area_min]
        centros=[]
        for c in candidatos:
            m=cv2.moments(c)
            if not m['m00']:continue
            u,v=m['m10']/m['m00'],m['m01']/m['m00']
            centros.append([u,v])
            x,y,w,h=cv2.boundingRect(c)
            cv2.rectangle(vista,(x,y),(x+w,y+h),(0,0,0),2)
            cv2.putText(vista,color,(x,max(20,y-5)),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,0,0),2)
        resultados[color]={'regiones':len(centros),'centros_pixel':centros}
        print(f'{color}: {len(centros)} regiones')
    cv2.imwrite(str(carpeta/'deteccion.png'),vista)
    (carpeta/'deteccion.json').write_text(json.dumps(resultados,indent=2),encoding='utf-8')
    print('Abre la imagen marcada: '+str((carpeta/'deteccion.png').resolve()))
    print('Son regiones de color, no una confirmación de cubo, coordenadas físicas ni agarre.')
    return 0


if __name__=='__main__':raise SystemExit(main())
