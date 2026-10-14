import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from resumir_interpretacion import resumir

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('csv',nargs='+');p.add_argument('--salida',required=True);a=p.parse_args()
    datos=resumir(a.csv)
    etiquetas=[f'{d["metodo"]}\n{d["condicion"]}'+('\nrespaldo' if d['degradada']=='True' else '') for d in datos]
    fig,ejes=plt.subplots(1,2,figsize=(max(8,len(datos)*2),4),layout='constrained')
    x=list(range(len(datos)))
    ejes[0].bar([i-.18 for i in x],[d['mediana_ms'] for d in datos],width=.36,label='Mediana')
    ejes[0].bar([i+.18 for i in x],[d['p95_ms'] for d in datos],width=.36,label='p95')
    ejes[0].set_ylabel('Latencia del servicio / evaluación local (ms)');ejes[0].legend()
    ejes[1].bar(x,[100*d['exactitud'] for d in datos]);ejes[1].set_ylim(0,100);ejes[1].set_ylabel('Exactitud de decisión (%)')
    for e in ejes:e.set_xticks(x,etiquetas);e.grid(axis='y',alpha=.2);e.set_axisbelow(True)
    fig.suptitle('Interpretación: resultados medidos en los CSV indicados')
    destino=Path(a.salida);destino.parent.mkdir(parents=True,exist_ok=True);fig.savefig(destino,dpi=180);plt.close(fig)
    print(f'Gráfica guardada en {destino}; verificar método/condición y procedencia antes de usar en informe.')
