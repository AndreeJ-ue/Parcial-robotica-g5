"""Herramientas de informe de las preguntas 1 y 3 (sin ROS)."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from comparar_metodos import comparar
from desglose_voz import fila_orden,fila_desglose


class P1(unittest.TestCase):
    def test_une_metodos_por_id(self):
        d={'permitido':True,'objeto':'cubo','color':'rojo','prioridad':1,'destino':'zona_a'}
        laya={'F01':{'id':'F01','categoria':'valida','frase':'x','metodo':'laya','degradada':'False','correcta':'True','decision_json':json.dumps(d)}}
        pal={'F01':{'id':'F01','categoria':'valida','frase':'x','metodo':'palabras_clave','degradada':'True','correcta':'False','decision_json':json.dumps({'permitido':False})}}
        f=comparar(laya,pal)[0]
        self.assertEqual((f['laya_decision'],f['palabras_decision'],f['laya_correcta']),('cubo/rojo/p1/zona_a','rechazar','True'))


class P3(unittest.TestCase):
    def datos(self,**extra):
        r={'success':True,'simulado':False,'message':'ok','wait_time_s':2.0,'preparacion_s':1.5,'percepcion_s':.4,
           'ik_s':.01,'planificacion_s':.09,'busqueda_s':0.0,'posicion_id':'P1','destino':'zona_rojo'}
        d={'modo':'voz','transcripcion':'Agarra el cubo rojo.','transcripcion_s':3.0,'decision_servicio_s':.2,
           'captura_post_habla_s':.5,'aceptado':True,'decision':{'color':'rojo','permitido':True,'metodo':'laya'},'resultado':r}
        d.update(extra);return d

    def test_desglose_suma_etapas(self):
        f=fila_desglose('a.json',self.datos())
        self.assertAlmostEqual(f['otros_preparacion'],1.0);self.assertAlmostEqual(f['total_s'],0.5+3.0+.2+2.0+1.5)
        self.assertTrue(f['inicio_en_busqueda'])

    def test_rechazo_no_entra_al_desglose(self):
        d=self.datos(aceptado=False,resultado={'success':False,'message':'Rechazada antes de encolar; revisar log/CSV del broker'})
        self.assertIsNone(fila_desglose('b.json',d));self.assertEqual(fila_orden('b.json',d)['que_hizo_el_brazo'],'rechazada antes de encolar')

    def test_modo_teclado_queda_registrado(self):
        d=self.datos(modo='teclado');d.pop('transcripcion');d['frase']='recoge el cubo rojo'
        self.assertEqual(fila_orden('c.json',d)['modo'],'teclado')


if __name__=='__main__':unittest.main()
