"""Comprobaciones de preparación; no inicia nodos ni movimiento."""
import argparse
import ast
import json
import xml.etree.ElementTree as ET
from _bootstrap import ROOT
from parcial_jetcobot.configuracion import cargar
from parcial_jetcobot.modelos import Pose


def pendientes(c):
    faltas=[]
    if not c.get('catalogo_confirmado'):faltas.append('catálogo físico sin confirmar')
    for n,z in c['zonas'].items():
        if not z.get('confirmada'):faltas.append(f'zona {n} sin calibrar')
        Pose(z['xyz_m'],z['quaternion_xyzw'],z['frame_id']).validar()
    for flag in ('modelo_confirmado','driver_trayectorias_validado','adaptador_serial_confirmado','escena_colisiones_confirmada'):
        if not c['hardware'].get(flag):faltas.append(flag)
    if len(c['hardware'].get('joint_names_moveit',[]))!=6: faltas.append('seis nombres MoveIt')
    for k in ('grupo_moveit','eef_link'):
        if not c['hardware'].get(k):faltas.append(k)
    for k in ('camara_fija','calibracion_confirmada'):
        if not c['camara'].get(k):faltas.append(k)
    if c['camara'].get('homografia_pixel_base_m') is None:faltas.append('homografía pixel→base')
    if c['interpretacion']['modo']!='laya':faltas.append('intérprete configurado para LAYA')
    return faltas


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=str,default=str(ROOT/'src/parcial_jetcobot/config/simulacion.json'))
    p.add_argument('--real',action='store_true');a=p.parse_args()
    cantidad=0
    for f in ROOT.rglob('*.py'):
        if '.git' in f.parts:continue
        ast.parse(f.read_text(encoding='utf-8-sig'),filename=str(f));cantidad+=1
    for f in (ROOT/'src').rglob('package.xml'):ET.parse(f)
    for f in (ROOT/'src/parcial_jetcobot/config').glob('*.json'):cargar(f)
    c=cargar(a.config);faltas=pendientes(c)
    print(f'Sintaxis: {cantidad} archivos Python. Metadatos/JSON legibles. Modo: {c["modo"]}.')
    for falta in faltas:print('PENDIENTE: '+falta)
    if a.real and (faltas or c['modo']!='real'):
        print('Configuración real incompleta. No habilitar hardware.');return 1
    print('Preparación estática correcta; ROS, drivers y hardware requieren comprobación en laboratorio.')
    return 0

if __name__=='__main__':raise SystemExit(main())
