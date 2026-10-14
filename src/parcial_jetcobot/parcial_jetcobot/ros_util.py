import threading
import time
from dataclasses import fields
from ament_index_python.packages import get_package_share_directory
from pathlib import Path
from .modelos import Decision, FalloTarea, Cancelado
from .configuracion import cargar


def configuracion_nodo(nodo):
    defecto = str(Path(get_package_share_directory('parcial_jetcobot'))/'config/simulacion.json')
    nodo.declare_parameter('config_file',defecto)
    return cargar(nodo.get_parameter('config_file').value)


def a_msg(decision, msg):
    for f in fields(Decision): setattr(msg,f.name,getattr(decision,f.name))
    return msg


def de_msg(msg):
    return Decision(**{f.name:getattr(msg,f.name) for f in fields(Decision)}).validar()


def llamar(cliente,req,limite_s,cancelado=lambda:False):
    fin = time.monotonic()+limite_s
    if not cliente.wait_for_service(timeout_sec=min(1.0,limite_s)):
        raise FalloTarea('Servicio no disponible')
    futuro = cliente.call_async(req)
    listo = threading.Event(); futuro.add_done_callback(lambda _:listo.set())
    while not listo.wait(0.02):
        if cancelado():
            futuro.cancel(); raise Cancelado('Cancelado durante llamada de servicio')
        if time.monotonic() >= fin:
            futuro.cancel(); raise FalloTarea('Tiempo límite de servicio excedido')
    respuesta = futuro.result()
    if respuesta is None: raise FalloTarea('Respuesta de servicio vacía')
    return respuesta
