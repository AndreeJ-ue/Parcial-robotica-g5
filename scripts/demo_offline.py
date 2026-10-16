"""Ensayo de lógica sin ROS, cámara ni puerto serial."""
import argparse,json
from dataclasses import asdict
from _bootstrap import ROOT
from parcial_jetcobot.configuracion import cargar
from parcial_jetcobot.clasificador import clasificar
from parcial_jetcobot.pipeline import BackendSimulado,ejecutar

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default=str(ROOT/'src/parcial_jetcobot/config/posiciones_fijas.articular.simulacion.json'))
    p.add_argument('--frase',action='append');a=p.parse_args();c=cargar(a.config);c['hardware']['retardo_simulado_s']=0
    if c['modo']!='simulado':p.error('Esta herramienta solo acepta configuraciones simuladas')
    frases=a.frase or ['Recoge el cubo rojo','Recoge la pelota roja','No recojas el cubo azul']
    for frase in frases:
        d=clasificar(frase,c);b=BackendSimulado(c);r=ejecutar(d,b,c)
        print(json.dumps({'frase':frase,'decision':d.dict(),'resultado':asdict(r),'operaciones_simuladas':b.operaciones},ensure_ascii=False))

if __name__=='__main__':main()
