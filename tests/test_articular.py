"""Modo articular (sin MoveIt): poses enseñadas, ROI del equipo y orden de la secuencia."""
import copy
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/parcial_jetcobot'),str(ROOT/'src/arm_broker')]
import cv2
from arm_broker import fk
from parcial_jetcobot.configuracion import cargar
from parcial_jetcobot.modelos import Decision,FalloTarea
from parcial_jetcobot.posiciones import validar,q_rad_de,usa_articular
from parcial_jetcobot.vision import mapa_posiciones
from parcial_jetcobot.pipeline import ejecutar,BackendSimulado
from parcial_jetcobot.articular import interpolar,error_fk_mm
from parcial_jetcobot.clasificador import clasificar

CONFIG=ROOT/'src/parcial_jetcobot/config'
def real():return cargar(CONFIG/'posiciones_fijas.articular.example.json')
def sim():
    c=cargar(CONFIG/'posiciones_fijas.articular.simulacion.json');c['hardware']['retardo_simulado_s']=0;return c
def decision(color='rojo'):return Decision('recoger_depositar','cubo',color,1,True,'por_color')


class Registrado(BackendSimulado):
    def __init__(self,c):super().__init__(c);self.registro=[];self.planes=[]
    def planificar(self,inicio,final):self.planes.append((list(inicio),list(final)));return super().planificar(inicio,final)
    def ik(self,pose,semilla):self.registro.append('ik');return super().ik(pose,semilla)
    def ejecutar(self,plan,cancelado):self.registro.append('mover');return super().ejecutar(plan,cancelado)
    def localizar(self,d):self.registro.append('detectar');return super().localizar(d)
    def pinza(self,abierta,cancelado):self.registro.append('abrir' if abierta else 'cerrar');return super().pinza(abierta,cancelado)


class Configuracion(unittest.TestCase):
    def test_plantilla_real_usa_modo_articular_y_no_se_habilita_sola(self):
        c=real();self.assertTrue(usa_articular(c));validar(c)
        with self.assertRaisesRegex(FalloTarea,'confirm'):validar(c,real=True)

    def test_todas_las_confirmaciones_habilitan_validacion_real(self):
        c=real();c['manipulacion']['busqueda']['confirmada']=True;c['camara']['calibracion_confirmada']=True
        for p in list(c['manipulacion']['posiciones'].values())+list(c['zonas'].values()):p['confirmada']=True
        validar(c,real=True)

    def test_poses_del_equipo_y_deposito_azul(self):
        c=real();m=c['manipulacion']
        self.assertEqual(m['busqueda']['q_grados'],[20,-8,-21,-54,0,-22])
        self.assertEqual(m['posiciones']['P1']['q_grados'],[3,-19,-109,31,0,-45])
        self.assertEqual(c['zonas']['zona_azul']['q_grados'],[123,-43,-55,0,-1,-33])
        for v,g in zip(m['busqueda']['q_rad'],m['busqueda']['q_grados']):self.assertAlmostEqual(v,math.radians(g))

    def test_pose_fuera_de_limites_se_rechaza(self):
        c=real();c['manipulacion']['posiciones']['P2']['q_grados'][1]=170
        with self.assertRaisesRegex(FalloTarea,'P2'):validar(c)

    def test_trayectorias_entre_poses_respetan_limites_paso_y_workspace(self):
        c=real();h=c['hardware'];b=c['manipulacion']['busqueda']['q_rad']
        for nombre,p in list(c['manipulacion']['posiciones'].items())+list(c['zonas'].items()):
            q=q_rad_de(p,nombre)
            for a,z in ((b,q),(q,b)):
                plan=interpolar(a,z,h['paso_plan_rad'],h['velocidad_articular_rad_s'])
                self.assertEqual(plan[0],(0.0,a));self.assertEqual(plan[-1][1],z)
                for (t0,q0),(t1,q1) in zip(plan,plan[1:]):
                    self.assertLessEqual(fk.paso_articular(q0,q1),h['paso_plan_rad']+1e-9);self.assertGreater(t1,t0)


class Vision(unittest.TestCase):
    def test_foto_del_equipo_en_busqueda_detecta_los_cuatro_colores(self):
        # Captura del equipo con el brazo en la postura de búsqueda; reescalada a la resolución calibrada.
        foto=cv2.imread(str(ROOT/'tests/datos/cubos_busqueda_equipo.jpeg'));self.assertIsNotNone(foto)
        c=real();foto=cv2.resize(foto,tuple(c['camara']['resolucion_calibracion_px']))
        self.assertEqual(mapa_posiciones(foto,c),{'P1':'rojo','P2':'verde','P3':'azul','P4':'amarillo'})


class Secuencia(unittest.TestCase):
    def test_orden_busqueda_camara_agarre_subida_deposito_retorno(self):
        c=sim();b=Registrado(c);r=ejecutar(decision('verde'),b,c)
        self.assertTrue(r.exito,r.motivo);self.assertEqual((r.posicion_id,r.destino),('P2','zona_verde'))
        self.assertEqual(b.registro,['mover','detectar','abrir','mover','cerrar','mover','mover','abrir','mover'])
        self.assertNotIn('ik',b.registro)
        q_b=c['manipulacion']['busqueda']['q_rad']
        q_p2=q_rad_de(c['manipulacion']['posiciones']['P2'],'P2');q_z=q_rad_de(c['zonas']['zona_verde'],'z')
        redondear=lambda q:[round(v,9) for v in q]
        self.assertEqual([(redondear(a),redondear(z)) for a,z in b.planes[1:]],
                         [(redondear(a),redondear(z)) for a,z in [(q_b,q_p2),(q_p2,q_b),(q_b,q_z),(q_z,q_b)]])
        self.assertEqual(b.estado(),q_b);self.assertEqual(r.error_fk_mm,-1)
        for etapa in ('busqueda','percepcion','cinematica_inversa','planificacion','gripper','movimiento','retorno'):
            self.assertIn(etapa,r.etapas_s)

    def test_prohibida_no_mueve(self):
        c=sim();b=Registrado(c);r=ejecutar(clasificar('No recojas el cubo azul',c),b,c)
        self.assertFalse(r.exito);self.assertEqual(b.registro,[])

    def test_objeto_ausente_solo_va_a_busqueda(self):
        c=sim();c['manipulacion']['mapa_simulado']['P1']=None;b=Registrado(c)
        r=ejecutar(decision('rojo'),b,c)
        self.assertFalse(r.exito);self.assertIn('ausente',r.motivo);self.assertEqual(b.registro,['mover','detectar'])

    def test_cancelacion_tras_cerrar_no_continua(self):
        c=sim();b=Registrado(c);r=ejecutar(decision(),b,c,lambda:'cerrar' in b.registro)
        self.assertFalse(r.exito);self.assertEqual(b.registro[-1],'cerrar')

    def test_error_fk_cero_si_llega_exacto(self):
        q=q_rad_de(real()['zonas']['zona_rojo'],'z');self.assertAlmostEqual(error_fk_mm(q,q),0.0)
        q2=list(q);q2[0]+=math.radians(1);self.assertGreater(error_fk_mm(q2,q),1.0)


class Herramientas(unittest.TestCase):
    def test_traza_va_y_vuelve_desde_busqueda_con_pasos_cortos(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from traza_poses import puntos
        c=real();q_b=c['manipulacion']['busqueda']['q_rad'];traza=puntos(c,'P2')
        q_p2=q_rad_de(c['manipulacion']['posiciones']['P2'],'P2')
        self.assertIn(q_p2,traza);self.assertEqual(traza[-1],q_b)
        for a,z in zip([q_b]+traza,traza):self.assertLessEqual(fk.paso_articular(a,z),c['hardware']['paso_plan_rad']+1e-9)
        with self.assertRaises(ValueError):puntos(c,'P9')

    def test_tabla_intentos_desde_tareas(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        import json
        from tabla_intentos import filas
        linea=json.dumps({'request_id':'r1','client_id':'integrante_1','frase':'Recoge el cubo rojo',
                          'decision':{'color':'rojo','prioridad':1,'degradada':True},'exito':True,'simulado':False,
                          'error_fk_mm':3.456,'error_fk_recogida_mm':-1,'wait_time_s':2.5,'posicion_id':'P1','destino':'zona_rojo','motivo':'ok'})
        f=filas([linea,''])[0]
        self.assertEqual((f['posicion_id'],f['error_fk_mm'],f['error_fk_recogida_mm'],f['exito_fisico']),('P1',3.46,'',''))


    def test_confirmar_config_habilita_validacion_real(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from confirmar_config import aplicar
        c=aplicar(real(),['busqueda','camara','pinza','P1','P2','P3','P4','zona_rojo','zona_verde','zona_azul','zona_amarillo'])
        validar(c,real=True);self.assertTrue(c['hardware']['adaptador_serial_confirmado'])
        with self.assertRaises(ValueError):aplicar(real(),['P7'])


if __name__=='__main__':unittest.main()
