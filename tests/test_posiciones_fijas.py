"""Pruebas sin ROS/hardware: regiones, permutaciones y orden de la cadena."""
import copy
import csv
import itertools
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/parcial_jetcobot'),str(ROOT/'src/arm_broker')]
import cv2
import numpy as np
from parcial_jetcobot.configuracion import cargar
from parcial_jetcobot.modelos import Decision,FalloTarea
from parcial_jetcobot.posiciones import validar,comprobar_busqueda,destino_para
from parcial_jetcobot.vision import mapa_posiciones,seleccionar_posicion
from parcial_jetcobot.pipeline import ejecutar,BackendSimulado
from parcial_jetcobot.clasificador import clasificar

COLORES=['rojo','azul','verde','amarillo']
BGR={'rojo':(0,0,255),'azul':(255,0,0),'verde':(0,255,0),'amarillo':(0,255,255)}
def config():return cargar(ROOT/'src/parcial_jetcobot/config/posiciones_fijas.simulacion.json')
def decision(color='rojo',destino='por_color'):
    return Decision('recoger_depositar','cubo',color,1,True,destino)
def imagen(c,mapa):
    frame=np.zeros((480,640,3),np.uint8)
    for n,color in mapa.items():
        if color is not None:
            x,y,w,h=c['manipulacion']['posiciones'][n]['roi_xywh']
            cv2.rectangle(frame,(x+15,y+15),(x+w-15,y+h-15),BGR[color],-1)
    return frame


class Regiones(unittest.TestCase):
    def test_24_permutaciones_seleccionan_posicion_y_no_color_fijo(self):
        c=config()
        for perm in itertools.permutations(COLORES):
            mapa=dict(zip(['P1','P2','P3','P4'],perm))
            with self.subTest(mapa=mapa):
                detectado=mapa_posiciones(imagen(c,mapa),c)
                self.assertEqual(detectado,mapa)
                for color in COLORES:
                    p,pose,_=seleccionar_posicion(detectado,decision(color),c)
                    self.assertEqual(mapa[p],color)
                    self.assertEqual(pose.xyz_m,c['manipulacion']['posiciones'][p]['xyz_m'])

    def test_ausente(self):
        c=config();mapa={'P1':'verde','P2':None,'P3':'amarillo','P4':'azul'}
        with self.assertRaisesRegex(FalloTarea,'ausente'):
            seleccionar_posicion(mapa_posiciones(imagen(c,mapa),c),decision(),c)

    def test_duplicado_solicitado(self):
        c=config();mapa={'P1':'rojo','P2':'rojo','P3':None,'P4':None}
        with self.assertRaisesRegex(FalloTarea,'duplicado'):
            seleccionar_posicion(mapa_posiciones(imagen(c,mapa),c),decision(),c)

    def test_region_dos_colores(self):
        c=config();f=imagen(c,dict.fromkeys(['P1','P2','P3','P4']))
        x,y,w,h=c['manipulacion']['posiciones']['P1']['roi_xywh']
        cv2.rectangle(f,(x+10,y+10),(x+70,y+h-10),BGR['rojo'],-1)
        cv2.rectangle(f,(x+90,y+10),(x+w-10,y+h-10),BGR['azul'],-1)
        with self.assertRaisesRegex(FalloTarea,'ambigua'):mapa_posiciones(f,c)

    def test_resolucion_no_calibrada(self):
        with self.assertRaisesRegex(FalloTarea,'Resolución'):mapa_posiciones(np.zeros((240,320,3),np.uint8),config())

    def test_vision_sin_coordenadas_de_movimiento(self):
        c=config();mapa=c['manipulacion']['mapa_simulado'];f=imagen(c,mapa)
        c['manipulacion']['busqueda']['q_rad']=None
        for p in c['manipulacion']['posiciones'].values():p['xyz_m']=None
        self.assertEqual(mapa_posiciones(f,c),mapa)

    def test_hsv_fuera_de_rango_no_se_trunca(self):
        c=config();c['camara']['hsv']['rojo'][0][1][0]=300
        with self.assertRaisesRegex(FalloTarea,'HSV'):mapa_posiciones(imagen(c,c['manipulacion']['mapa_simulado']),c)

    def test_regiones_solapadas(self):
        c=config();c['manipulacion']['posiciones']['P2']['roi_xywh']=c['manipulacion']['posiciones']['P1']['roi_xywh']
        with self.assertRaisesRegex(FalloTarea,'solaparse'):validar(c)

    def test_roi_fuera_de_imagen(self):
        c=config();c['manipulacion']['posiciones']['P1']['roi_xywh']=[630,0,20,20]
        with self.assertRaisesRegex(FalloTarea,'fuera'):validar(c)

    def test_no_reconoce_otra_forma_por_color(self):
        c=config();d=decision();d.objeto='pelota'
        with self.assertRaisesRegex(FalloTarea,'tipo'):seleccionar_posicion(c['manipulacion']['mapa_simulado'],d,c)

    def test_plantilla_real_no_habilitable_sin_mediciones(self):
        c=cargar(ROOT/'src/parcial_jetcobot/config/posiciones_fijas.example.json')
        with self.assertRaises(FalloTarea):validar(c,real=True)

    def test_ejemplo_simulado_no_se_convierte_en_calibracion_real(self):
        with self.assertRaises(FalloTarea):validar(config(),real=True)

    def test_fuera_de_busqueda(self):
        with self.assertRaisesRegex(FalloTarea,'fuera'):comprobar_busqueda([0]*6,config())


class BackendRegistrado(BackendSimulado):
    def __init__(self,c):super().__init__(c);self.registro=[];self.planes=0
    def planificar(self,inicio,final):
        self.planes+=1;self.registro.append('plan');return super().planificar(inicio,final)
    def ik(self,pose,semilla):self.registro.append('ik');return super().ik(pose,semilla)
    def ejecutar(self,plan,cancelado):self.registro.append('mover');return super().ejecutar(plan,cancelado)
    def localizar(self,d):
        comprobar_busqueda(self.estado(),self.config);self.registro.append('detectar');return super().localizar(d)
    def pinza(self,abierta,cancelado):
        self.registro.append('abrir' if abierta else 'cerrar');return super().pinza(abierta,cancelado)


class Cadena(unittest.TestCase):
    def test_semilla_medida_orienta_ik_pero_no_se_reproduce_como_comando(self):
        c=config();qref=[.2,.3,.4,.5,.6,.7]
        c['manipulacion']['posiciones']['P2']['semilla_ik_rad']=qref
        b=BackendRegistrado(c);original=b.ik;semillas=[]
        def registrar(pose,s):semillas.append(list(s));return original(pose,s)
        b.ik=registrar;r=ejecutar(decision(),b,c)
        self.assertTrue(r.exito,r.motivo);self.assertEqual(len(semillas),6);self.assertEqual(semillas[1],qref)
        self.assertNotEqual(b.estado(),qref)

    def test_referencias_confirmadas_no_habilitan_plantilla_real(self):
        c=cargar(ROOT/'src/parcial_jetcobot/config/posiciones_fijas.mediciones.example.json')
        self.assertEqual(c['manipulacion']['posiciones']['P1']['q_referencia_grados'],[3,-19,-109,31,0,-45])
        self.assertEqual(c['zonas']['zona_rojo']['q_referencia_grados'],[87,-49,-48,0,-1,-33])
        with self.assertRaises(FalloTarea):validar(c,real=True)

    def test_conversion_de_las_ocho_referencias_conserva_rotacion(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from revisar_posturas_p2 import revisar
        datos=json.loads((ROOT/'referencias/posturas_compartidas_p2.json').read_text(encoding='utf-8'))
        resultado=revisar(datos);self.assertEqual(len(resultado['posturas']),8)
        for p in resultado['posturas']:
            x,y,z,w=p['fk_derivada_quaternion_xyzw']
            rot=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                 [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                 [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
            for i in range(3):
                for j in range(3):self.assertAlmostEqual(rot[i][j],p['fk_derivada_matriz'][i][j],places=12)
            self.assertTrue(p['limites_rb2_ok']);self.assertFalse(p['urdf_verificado'])

    def test_clasificador_conserva_las_50_etiquetas_de_desarrollo(self):
        c=cargar(ROOT/'src/parcial_jetcobot/config/simulacion.json')
        with (ROOT/'datos/frases_50.csv').open(encoding='utf-8-sig',newline='') as f:filas=list(csv.DictReader(f))
        self.assertEqual(len(filas),50)
        for fila in filas:
            with self.subTest(frase=fila['frase']):
                d=clasificar(fila['frase'],c);permitido=fila['permitido']=='true'
                self.assertEqual(d.permitido,permitido);self.assertEqual(d.accion,fila['accion'])
                if permitido:
                    for campo in ('objeto','color','prioridad','destino'):self.assertEqual(str(getattr(d,campo)),fila[campo])

    def test_estrategia_sin_posiciones_no_mueve(self):
        c=cargar(ROOT/'src/parcial_jetcobot/config/simulacion.json');b=BackendRegistrado(c)
        r=ejecutar(clasificar('Recoge el cubo rojo',c),b,c)
        self.assertFalse(r.exito);self.assertIn('no soportada',r.motivo);self.assertEqual(b.registro,[])

    def test_busqueda_desactualizada_despues_de_captura_no_recoge(self):
        c=config();b=BackendRegistrado(c);original=b.localizar
        def se_movio(d):
            p=original(d);b.q[0]+=.1;return p
        b.localizar=se_movio;r=ejecutar(decision(),b,c)
        self.assertFalse(r.exito);self.assertNotIn('abrir',b.registro)

    def test_busqueda_antes_de_deteccion_y_retorno_al_final(self):
        c=config();b=BackendRegistrado(c);r=ejecutar(decision(),b,c)
        self.assertTrue(r.exito,r.motivo);self.assertTrue(r.simulado)
        self.assertEqual(r.posicion_id,'P2');self.assertEqual(r.destino,'zona_rojo')
        self.assertEqual(b.estado(),c['manipulacion']['busqueda']['q_rad'])
        self.assertLess(b.registro.index('mover'),b.registro.index('detectar'))
        self.assertEqual(b.registro.count('ik'),6)
        self.assertEqual(b.planes,8)
        self.assertEqual(b.registro[-1],'mover')
        self.assertEqual(r.error_fk_mm,-1);self.assertEqual(r.inicio_movimiento_wall_ns,0)
        self.assertIn('busqueda',r.etapas_s);self.assertIn('retorno',r.etapas_s)

    def test_no_repite_busqueda_si_ya_esta_en_postura(self):
        c=config();b=BackendRegistrado(c);b.q=list(c['manipulacion']['busqueda']['q_rad'])
        r=ejecutar(decision(),b,c)
        self.assertTrue(r.exito,r.motivo);self.assertEqual(b.registro[0],'detectar');self.assertEqual(b.planes,7)

    def test_nueva_permutacion_se_consulta_en_cada_pedido(self):
        c=config();b=BackendRegistrado(c);r1=ejecutar(decision(),b,c)
        c['manipulacion']['mapa_simulado']={'P1':'rojo','P2':'verde','P3':'amarillo','P4':'azul'}
        r2=ejecutar(decision(),b,c)
        self.assertEqual((r1.posicion_id,r2.posicion_id),('P2','P1'))

    def test_prohibida_no_busca_ni_acciona_pinza(self):
        c=config();b=BackendRegistrado(c);d=decision();d.permitido=False
        r=ejecutar(d,b,c);self.assertFalse(r.exito);self.assertEqual(b.registro,[])

    def test_ausente_no_inicia_recogida(self):
        c=config();c['manipulacion']['mapa_simulado']['P2']=None;b=BackendRegistrado(c)
        r=ejecutar(decision(),b,c)
        self.assertFalse(r.exito);self.assertEqual(b.registro.count('mover'),1)
        self.assertNotIn('abrir',b.registro);self.assertNotIn('ik',b.registro)

    def test_ultimo_plan_falla_antes_de_pinza_o_recogida(self):
        c=config();b=BackendRegistrado(c);original=b.planificar
        def fallar(inicio,final):
            if b.planes==7:raise FalloTarea('Retorno imposible')
            return original(inicio,final)
        b.planificar=fallar;r=ejecutar(decision(),b,c)
        self.assertFalse(r.exito);self.assertEqual(b.registro.count('mover'),1);self.assertNotIn('abrir',b.registro)

    def test_cancelacion_despues_de_agarrar_no_continua(self):
        c=config();b=BackendRegistrado(c)
        r=ejecutar(decision(),b,c,lambda:'cerrar' in b.registro)
        self.assertFalse(r.exito);self.assertEqual(b.registro[-1],'cerrar')

    def test_pose_servidor_no_coincide_con_slot(self):
        c=config();b=BackendRegistrado(c);original=b.localizar
        def alterada(d):
            p=original(d);p.xyz_m[0]+=.01;return p
        b.localizar=alterada;r=ejecutar(decision(),b,c)
        self.assertFalse(r.exito);self.assertNotIn('abrir',b.registro)

    def test_config_sin_mediciones_no_mueve(self):
        c=config();c['manipulacion']['posiciones']['P3']['xyz_m']=None;b=BackendRegistrado(c)
        r=ejecutar(decision(),b,c)
        self.assertFalse(r.exito);self.assertEqual(b.registro,[])

    def test_destino_explicito_tiene_precedencia(self):
        c=config();b=BackendRegistrado(c);r=ejecutar(decision(destino='zona_azul'),b,c)
        self.assertTrue(r.exito,r.motivo);self.assertEqual(r.destino,'zona_azul')

    def test_clasificador_destino_por_color(self):
        c=config();d=clasificar('Recoge el cubo rojo',c)
        self.assertTrue(d.permitido);self.assertEqual(d.destino,'por_color');self.assertEqual(destino_para(d,c),'zona_rojo')

    def test_clasificador_destino_explicito(self):
        c=config();d=clasificar('Recoge el cubo rojo en la zona azul',c)
        self.assertTrue(d.permitido);self.assertEqual(d.destino,'zona_azul')

    def test_admision_distingue_color_de_objeto_y_zona(self):
        from parcial_jetcobot.admision import validar_color_explicito
        self.assertEqual(validar_color_explicito('Recoge el cubo rojo en la zona azul',decision()).color,'rojo')

    def test_mapas_inconsistentes_no_inician_agarre(self):
        c=config();b=BackendRegistrado(c);original=b.localizar
        def incorrecta(d):
            p=original(d);b.posicion_id='P1';return p
        b.localizar=incorrecta;r=ejecutar(decision(),b,c)
        self.assertFalse(r.exito);self.assertNotIn('abrir',b.registro)

if __name__=='__main__':unittest.main()
