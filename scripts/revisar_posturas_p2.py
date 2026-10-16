"""Convierte referencias articulares y calcula FK; no conecta ROS ni serial."""
import argparse,json,math
from pathlib import Path
from _bootstrap import ROOT
from arm_broker.fk import fk_matriz,dentro_de_limites,dentro_del_workspace


def quaternion(r):
    tr=r[0][0]+r[1][1]+r[2][2]
    if tr>0:
        s=math.sqrt(tr+1)*2
        q=[(r[2][1]-r[1][2])/s,(r[0][2]-r[2][0])/s,(r[1][0]-r[0][1])/s,s/4]
    elif r[0][0]>r[1][1] and r[0][0]>r[2][2]:
        s=math.sqrt(1+r[0][0]-r[1][1]-r[2][2])*2
        q=[s/4,(r[0][1]+r[1][0])/s,(r[0][2]+r[2][0])/s,(r[2][1]-r[1][2])/s]
    elif r[1][1]>r[2][2]:
        s=math.sqrt(1+r[1][1]-r[0][0]-r[2][2])*2
        q=[(r[0][1]+r[1][0])/s,s/4,(r[1][2]+r[2][1])/s,(r[0][2]-r[2][0])/s]
    else:
        s=math.sqrt(1+r[2][2]-r[0][0]-r[1][1])*2
        q=[(r[0][2]+r[2][0])/s,(r[1][2]+r[2][1])/s,s/4,(r[1][0]-r[0][1])/s]
    norma=math.sqrt(sum(v*v for v in q))
    return [v/norma for v in q]


def revisar(datos):
    salida={'roles_confirmados':bool(datos.get('roles_confirmados')), 'no_es_calibracion_fisica':True,
            'nota':'FK derivada del DH del repositorio. Verificar URDF, ejes, herramienta y marco antes de usarla como objetivo.', 'posturas':[]}
    for grupo in ('posiciones','depositos_por_color'):
        for nombre,p in datos[grupo].items():
            grados=p['q_grados']
            if len(grados)!=6 or not all(type(v) in (int,float) and math.isfinite(v) for v in grados):raise ValueError('Faltan seis ángulos finitos')
            q=[math.radians(v) for v in grados];t=fk_matriz(q)
            ok,motivo=dentro_de_limites(q);workspace,razon=dentro_del_workspace(q)
            salida['posturas'].append({'grupo':grupo,'nombre':nombre,'q_grados':grados,'q_radianes':q,
                'g7':p.get('g7'),'limites_rb2_ok':ok,'motivo_limites':motivo,
                'workspace_rb2_ok':workspace,'motivo_workspace':razon,
                'fk_derivada_xyz_m':[t[i][3]/1000 for i in range(3)],'fk_derivada_quaternion_xyzw':quaternion(t),'fk_derivada_matriz':t,
                'urdf_verificado':False})
    return salida


def sugerir_configuracion(resultado):
    if not resultado['roles_confirmados']:raise ValueError('Confirmar roles/unidades antes de generar una sugerencia')
    c=json.loads((ROOT/'src/parcial_jetcobot/config/posiciones_fijas.example.json').read_text(encoding='utf-8-sig'))
    for p in resultado['posturas']:
        destino=(c['manipulacion']['posiciones'][p['nombre']] if p['grupo']=='posiciones' else
                 c['zonas'][c['manipulacion']['destinos_por_color'][p['nombre']]])
        destino.update(xyz_m=p['fk_derivada_xyz_m'],quaternion_xyzw=p['fk_derivada_quaternion_xyzw'],
                       semilla_ik_rad=p['q_radianes'],q_referencia_grados=p['q_grados'],confirmada=False,
                       origen_geometria='FK del DH del repositorio; pendiente de contrastar con URDF y herramienta real')
    c['manipulacion']['nota']='Referencias confirmadas de la captura del grupo. XYZ/orientación derivados de FK, no calibración validada. Completar búsqueda/ROI y verificar geometría antes de confirmar.'
    return c


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--entrada',default=str(ROOT/'referencias/posturas_compartidas_p2.json'))
    p.add_argument('--salida');p.add_argument('--config-sugerida');a=p.parse_args()
    resultado=revisar(json.loads(Path(a.entrada).read_text(encoding='utf-8-sig')))
    texto=json.dumps(resultado,indent=2,ensure_ascii=False)
    if a.salida:
        destino=Path(a.salida)
        if destino.exists():p.error('Elegir una salida nueva; no sobrescribir mediciones')
        destino.parent.mkdir(parents=True,exist_ok=True);destino.write_text(texto+'\n',encoding='utf-8')
    if a.config_sugerida:
        destino=Path(a.config_sugerida)
        if destino.exists():p.error('La configuración sugerida no debe sobrescribir un archivo existente')
        destino.parent.mkdir(parents=True,exist_ok=True)
        destino.write_text(json.dumps(sugerir_configuracion(resultado),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(texto)
