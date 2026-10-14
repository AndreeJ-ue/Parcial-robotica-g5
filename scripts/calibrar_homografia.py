"""Ajusta usando mediciones; valida en puntos independientes y no activa hardware."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np


def calibrar(datos):
    puntos=datos['puntos']
    ajuste=[p for p in puntos if p.get('uso','ajuste')=='ajuste']
    validacion=[p for p in puntos if p.get('uso')=='validacion']
    if len(ajuste)<4 or len(validacion)<2:raise ValueError('Se necesitan 4 puntos de ajuste y al menos 2 independientes para validar')
    def matriz(puntos,k):
        a=np.asarray([p[k] for p in puntos],dtype=float)
        if a.shape!=(len(puntos),2) or not np.isfinite(a).all():raise ValueError('Faltan mediciones finitas UV/XY')
        return a
    u=matriz(ajuste,'pixel_uv');xy=matriz(ajuste,'base_xy_m')
    h,_=cv2.findHomography(u,xy,method=0)
    if h is None or abs(np.linalg.det(h))<1e-15:raise ValueError('Puntos degenerados; repetir medición')
    v=matriz(validacion,'pixel_uv');real=matriz(validacion,'base_xy_m')
    pred=cv2.perspectiveTransform(v.reshape(-1,1,2),h).reshape(-1,2)
    errores=np.linalg.norm(real-pred,axis=1)*1000
    return dict(confirmada=False,homografia_pixel_base_m=h.tolist(),errores_validacion_mm=errores.tolist(),
                error_max_mm=float(errores.max()),error_medio_mm=float(errores.mean()),
                advertencia='Revisar tolerancia del curso, cámara fija y plano/altura antes de confirmar configuración')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mediciones');p.add_argument('--salida',required=True);a=p.parse_args()
    resultado=calibrar(json.loads(Path(a.mediciones).read_text(encoding='utf-8-sig')))
    Path(a.salida).write_text(json.dumps(resultado,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(resultado,ensure_ascii=False,indent=2))
