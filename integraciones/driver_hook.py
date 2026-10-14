"""Adaptador para integrar EN el driver existente, compartiendo mc y el mismo lock.

No ejecutar como segundo proceso ni abrir otro MyCobot. Revisar sync_plan_nx antes
de instalar. El callback que envía ángulos debe usar también el lock recibido.
"""
import math
import threading
import time
from sensor_msgs.msg import JointState
from arm_broker_interfaces.srv import AccionarPinza


def instalar(node,mc,serial_lock,nombres,abierto=100,cerrado=0,velocidad=50):
    if len(nombres)!=6:raise ValueError('se requieren seis nombres en orden del firmware')
    pub=node.create_publisher(JointState,'/arm/joint_states_measured',10)
    def medir():
        with serial_lock:q=mc.get_angles()
        if not q or len(q)!=6:return
        msg=JointState();msg.header.stamp=node.get_clock().now().to_msg()
        msg.name=list(nombres);msg.position=[math.radians(x) for x in q];pub.publish(msg)
    def pinza(req,res):
        if not 0<req.timeout_s<=15:
            res.motivo='Tiempo límite fuera de rango';return res
        try:
            with serial_lock:
                mc.set_gripper_value(abierto if req.abrir else cerrado,velocidad)
                time.sleep(0.2);limite=time.monotonic()+req.timeout_s
                while True:
                    estado=mc.is_gripper_moving()
                    if estado==0:break
                    if estado!=1:raise RuntimeError('Pinza no respondió con estado válido')
                    if time.monotonic()>limite:raise TimeoutError('Pinza no confirmó fin')
                    time.sleep(0.05)
                valor=mc.get_gripper_value()
                esperado=abierto if req.abrir else cerrado
                if valor is None or abs(valor-esperado)>10:
                    raise RuntimeError('Apertura de pinza no confirmada; ajustar umbral al agarre real')
            res.completado=True
        except Exception as exc:res.motivo=str(exc)
        return res
    timer=node.create_timer(0.2,medir)
    servicio=node.create_service(AccionarPinza,'/arm/accionar_pinza',pinza)
    return pub,timer,servicio
