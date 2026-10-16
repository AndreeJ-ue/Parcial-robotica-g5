import csv
import json
import math
import statistics
import sys
from collections import defaultdict

def percentil(valores,p=.95):
    v=sorted(valores)
    return v[max(0,math.ceil(len(v)*p)-1)]

def resumir(rutas):
    grupos=defaultdict(list)
    for ruta in rutas:
        with open(ruta,encoding='utf-8-sig',newline='') as f:
            for fila in csv.DictReader(f):
                grupos[(fila['dataset_sha256'],fila['condicion'],fila['metodo'],fila['degradada'])].append(fila)
    resultado=[]
    for (sha,condicion,metodo,degradada),filas in grupos.items():
        tiempos=[float(f['latencia_servicio_ms']) for f in filas]
        r=dict(sha256=sha,condicion=condicion,metodo=metodo,degradada=degradada,
               n=len(filas),exactitud=sum(f['correcta']=='True' for f in filas)/len(filas),
               mediana_ms=statistics.median(tiempos),p95_ms=percentil(tiempos))
        for campo in ('http_ms','calculo_servidor_ms','resto_http_ms'):
            validos=[float(f[campo]) for f in filas if f[campo] and float(f[campo])>=0]
            r[campo+'_mediana']=statistics.median(validos) if validos else None
        resultado.append(r)
    return resultado

if __name__=='__main__':
    if len(sys.argv)<2:raise SystemExit('Uso: resumir_interpretacion.py archivo.csv [otro.csv]')
    print(json.dumps(resumir(sys.argv[1:]),ensure_ascii=False,indent=2))
