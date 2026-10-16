"""Adaptador serial con doble de MyCobot; nunca abre un puerto real."""
import importlib.util
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

class PuertoFalso:
    def __init__(self,*args):self.enviados=[];self.pinzados=[];self.angulos=[1,2,3,4,5,6];self.moviendo=lambda:0
    def get_angles(self):return self.angulos
    def get_fresh_mode(self):return 1
    def send_angles(self,q,v):self.enviados.append((q,v))
    def set_gripper_value(self,q,v):self.pinzados.append((q,v))
    def is_gripper_moving(self):return self.moviendo()
    def get_gripper_value(self):return 100

class Mensaje:
    def __init__(self):self.header=types.SimpleNamespace(stamp=None)

class NodoFalso:
    def __init__(self,*a):self.parametros={};self.mensajes=[]
    def declare_parameter(self,k,v):self.parametros[k]=v
    def get_parameter(self,k):return types.SimpleNamespace(value=self.parametros[k])
    def create_publisher(self,*a):return types.SimpleNamespace(publish=self.mensajes.append)
    def create_subscription(self,*a,**kw):return object()
    def create_timer(self,*a,**kw):return object()
    def create_service(self,*a,**kw):return object()
    def get_clock(self):return types.SimpleNamespace(now=lambda:types.SimpleNamespace(to_msg=lambda:None))
    def get_logger(self):return types.SimpleNamespace(info=lambda *a:None,error=lambda *a:None,warn=lambda *a:None)

def cargar_driver():
    modulos={}
    def modulo(nombre,**datos):
        m=types.ModuleType(nombre);m.__dict__.update(datos);modulos[nombre]=m
    modulo('rclpy');modulo('rclpy.node',Node=NodoFalso)
    modulo('rclpy.callback_groups',MutuallyExclusiveCallbackGroup=object)
    modulo('rclpy.executors',MultiThreadedExecutor=object)
    modulo('sensor_msgs');modulo('sensor_msgs.msg',JointState=Mensaje)
    modulo('pymycobot');modulo('pymycobot.mycobot',MyCobot=PuertoFalso)
    modulo('arm_broker_interfaces');modulo('arm_broker_interfaces.srv',AccionarPinza=object)
    with patch.dict(sys.modules,modulos):
        spec=importlib.util.spec_from_file_location('driver_prueba_p2',ROOT/'integraciones/sync_plan_p2.py')
        driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    return driver

driver=cargar_driver()

class Serial(unittest.TestCase):
    def test_arranque_sin_home_ni_pinza(self):
        n=driver.DriverP2();self.assertEqual(n.mc.enviados,[]);self.assertEqual(n.mc.pinzados,[])

    def test_comandos_inhabilitados(self):
        n=driver.DriverP2();n.listener_callback(types.SimpleNamespace(name=driver.NOMBRES,position=[0]*6))
        self.assertEqual(n.mc.enviados,[])

    def test_lectura_publicada_en_radianes(self):
        n=driver.DriverP2();n.medir()
        self.assertEqual(n.mensajes[0].name,driver.NOMBRES)
        self.assertAlmostEqual(n.mensajes[0].position[0],.017453292519943295)

    def test_mediciones_se_intercalan_mientras_espera_pinza(self):
        n=driver.DriverP2();n.parametros['habilitar_comandos']=True
        consultando=threading.Event();medido=threading.Event()
        def moviendo():consultando.set();return 0 if medido.is_set() else 1
        n.mc.moviendo=moviendo;res=types.SimpleNamespace(completado=False,motivo='')
        hilo=threading.Thread(target=lambda:n.pinza(types.SimpleNamespace(abrir=True,timeout_s=2),res))
        hilo.start()
        try:
            self.assertTrue(consultando.wait(1))
            # Debe poder tomar el mutex entre consultas de pinza, antes de que termine.
            pudo=n.serial_lock.acquire(timeout=.3)
            self.assertTrue(pudo,'La espera de pinza bloqueó todas las mediciones')
            if pudo:
                try:n.medir();medido.set()
                finally:n.serial_lock.release()
        finally:
            medido.set();hilo.join(timeout=3)
        self.assertFalse(hilo.is_alive());self.assertTrue(res.completado);self.assertEqual(len(n.mensajes),1)

    def test_pinza_timeout_no_declara_exito(self):
        n=driver.DriverP2();n.parametros['habilitar_comandos']=True;n.mc.moviendo=lambda:1
        res=types.SimpleNamespace(completado=False,motivo='')
        n.pinza(types.SimpleNamespace(abrir=False,timeout_s=.05),res)
        self.assertFalse(res.completado);self.assertIn('plazo',res.motivo)

if __name__=='__main__':unittest.main()
