"""Detecta y anota regiones desde una fotografía, sin ROS, serial ni movimientos."""
import argparse,json
from pathlib import Path
from _bootstrap import ROOT
import cv2
from parcial_jetcobot.configuracion import cargar
from parcial_jetcobot.vision import mapa_posiciones,seleccionar_posicion
from parcial_jetcobot.modelos import Decision

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--config',required=True);p.add_argument('--imagen',required=True)
 p.add_argument('--color');p.add_argument('--salida',required=True)
 a=p.parse_args();c=cargar(a.config);frame=cv2.imread(a.imagen)
 if frame is None:p.error('No se pudo leer la imagen')
 salida=Path(a.salida);salida.mkdir(parents=True,exist_ok=False)
 mapa=mapa_posiciones(frame,c);datos={'mapa_colores':mapa,'seleccion':None,'solo_imagen':True}
 if a.color:
  try:
   nombre,pose,altura=seleccionar_posicion(mapa,Decision('recoger_depositar','cubo',a.color,1,True,'por_color'),c)
   datos['seleccion']={'posicion_id':nombre,'xyz_m':pose.xyz_m,'frame_id':pose.frame_id,'altura_aproximacion_m':altura}
  except RuntimeError as exc:datos['error_seleccion']=str(exc)
 for nombre,slot in c['manipulacion']['posiciones'].items():
  x,y,w,h=slot['roi_xywh'];cv2.rectangle(frame,(x,y),(x+w,y+h),(255,255,255),2)
  cv2.putText(frame,f'{nombre}: {mapa[nombre]}',(x,y+20),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
 cv2.imwrite(str(salida/'regiones.png'),frame)
 (salida/'mapa.json').write_text(json.dumps(datos,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(datos,ensure_ascii=False,indent=2))
 return 1 if 'error_seleccion' in datos else 0

if __name__=='__main__':raise SystemExit(main())
