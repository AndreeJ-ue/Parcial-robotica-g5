import json
from _bootstrap import ROOT
from parcial_jetcobot.configuracion import cargar
from parcial_jetcobot.clasificador import clasificar
from parcial_jetcobot.pipeline import BackendSimulado,ejecutar

c=cargar(ROOT/'src/parcial_jetcobot/config/simulacion.json')
for frase in ('Recoge el cubo rojo en la zona a','Recoge la pelota roja','No recojas el cubo azul'):
    d=clasificar(frase,c);b=BackendSimulado(c)
    r=ejecutar(d,b,c)
    print(json.dumps({'frase':frase,'permitido':d.permitido,'exito_simulado':r.exito,
                      'motivo':r.motivo,'operaciones':b.operaciones,'error_fk_mm':r.error_fk_mm},ensure_ascii=False))
