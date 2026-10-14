import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/parcial_jetcobot'))
"""Ensayo parcial: respaldo local -> acción RB2 -> giro J1 de tres grados.

No recoge objetos, no abre pinza ni sustituye IK/MoveIt. Usa lectura física reciente o seis ángulos actuales declarados por el operador.
Requiere un único broker RB2 y un driver compatible.
"""
import argparse
import math
import time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from sensor_msgs.msg import JointState
from arm_broker_interfaces.action import MoveArm
from parcial_jetcobot.clasificador import clasificar

NOMBRES=['1_Joint','2_Joint','3_Joint','4_Joint','5_Joint','6_Joint']


def esperar(nodo,futuro,plazo):
    rclpy.spin_until_future_complete(nodo,futuro,timeout_sec=plazo)
    if not futuro.done():
        futuro.cancel()
        raise RuntimeError('No llegó respuesta del broker dentro del plazo')
    return futuro.result()


def esperar_broker(nodo,plazo=8):
    limite=time.monotonic()+plazo
    estable_desde=None
    endpoints=[]
    while time.monotonic()<limite:
        rclpy.spin_once(nodo,timeout_sec=.2)
        endpoints=nodo.get_publishers_info_by_topic('/joint_states')
        vistos=[{'nombre':e.node_name,'namespace':e.node_namespace} for e in endpoints]
        if len(endpoints)>1:
            raise RuntimeError('Varios publicadores de comandos: '+str(vistos))
        if len(endpoints)==1 and endpoints[0].node_name=='arm_broker':
            if estable_desde is None:estable_desde=time.monotonic()
            if time.monotonic()-estable_desde>=1:
                print('Publicador descubierto:',vistos)
                return
        else:
            # Un endpoint puede descubrirse antes que su identidad ROS completa.
            estable_desde=None
    vistos=[{'nombre':e.node_name,'namespace':e.node_namespace} for e in endpoints]
    raise RuntimeError('No se confirmó arm_broker dentro del plazo. Publicadores vistos: '+str(vistos))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('frase')
    p.add_argument('--sin-mediciones',action='store_true',
                   help='Para driver original: exige --q-inicial-grados con seis ángulos actuales')
    p.add_argument('--q-inicial-grados',type=float,nargs=6,metavar='GRADOS')
    a=p.parse_args()
    if a.sin_mediciones and (not a.q_inicial_grados or not all(math.isfinite(v) for v in a.q_inicial_grados)):
        p.error("--sin-mediciones requiere --q-inicial-grados con seis valores actuales")
    d=clasificar(a.frase,{'zonas':{'zona_a':{}},'destino_por_defecto':'zona_a'},degradada=True,
                 motivo='Ensayo con respaldo local; no consulta LAYA')
    print('Decisión:',d.dict())
    if not d.permitido:
        print('RECHAZADA: no se enviará ninguna acción.')
        return 0
    if (d.objeto,d.color,d.destino)!=('cubo','rojo','zona_a'):
        print('Este ensayo físico solo admite cubo rojo y zona a.')
        return 1
    rclpy.init();n=Node('ensayo_frase_movimiento');muestras=[]
    def recibir(msg):
        if len(msg.name)!=len(msg.position):return
        q=dict(zip(msg.name,msg.position))
        if all(k in q for k in NOMBRES):
            valores=[q[k] for k in NOMBRES]
            if all(math.isfinite(v) for v in valores):muestras.append((time.monotonic(),valores))
    sub=n.create_subscription(JointState,'/arm/joint_states_measured',recibir,10)
    # Observador de lectura para que el servidor de descubrimiento anuncie
    # los endpoints del tópico de comandos a este cliente. No publica nada.
    observador=n.create_subscription(JointState,'/joint_states',lambda msg:None,10)
    cliente=ActionClient(n,MoveArm,'/move_arm')
    handle=None
    try:
        if not a.sin_mediciones:
            limite=time.monotonic()+5
            while not muestras and time.monotonic()<limite:rclpy.spin_once(n,timeout_sec=.2)
            if not muestras:raise RuntimeError('No hay lectura física del driver')
        esperar_broker(n)
        q=[math.radians(v) for v in a.q_inicial_grados] if a.sin_mediciones else muestras[-1][1]
        if not a.sin_mediciones and time.monotonic()-muestras[-1][0]>2:
            raise RuntimeError('La lectura física tiene más de dos segundos')
        if a.sin_mediciones:
            print('Postura actual declarada por el operador; no hay lectura automática.')
        if not cliente.wait_for_server(timeout_sec=3):raise RuntimeError('No aparece /move_arm')
        objetivo=list(q);objetivo[0]+=math.radians(3)
        goal=MoveArm.Goal();goal.joint_positions=objetivo
        goal.client_id='ensayo_rojo';goal.priority=d.prioridad
        print('Movimiento de prueba: J1 +3 grados; pinza sin cambios. No es un pick and place.')
        handle=esperar(n,cliente.send_goal_async(goal),5)
        if not handle.accepted:raise RuntimeError('Broker rechazó la admisión')
        respuesta=esperar(n,handle.get_result_async(),20).result
        print('Resultado broker:',respuesta.success,respuesta.message)
        rclpy.spin_once(n,timeout_sec=.5)
        if not a.sin_mediciones and muestras:
            reciente=muestras[-1]
            if time.monotonic()-reciente[0]<2:
                print('Última lectura física en grados:',[round(math.degrees(v),2) for v in reciente[1]])
        print('El resultado del broker confirma envío; observa el giro real para confirmar el ensayo.')
        return 0 if respuesta.success else 1
    except (RuntimeError,KeyboardInterrupt) as exc:
        print('Ensayo interrumpido:',exc)
        if handle is not None and handle.accepted:
            try:esperar(n,handle.cancel_goal_async(),2)
            except RuntimeError:pass
        return 1
    finally:
        cliente.destroy();n.destroy_node()
        if rclpy.ok():rclpy.shutdown()


if __name__=='__main__':raise SystemExit(main())
