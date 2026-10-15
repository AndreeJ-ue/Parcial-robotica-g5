""" Figura del desglose de tiempos voz → movimiento — Pregunta 3, Parte C """

""" Lee un CSV con dos columnas (etapa, mediana_s) y dibuja un gráfico de barras con el
porcentaje de cada etapa sobre el total voz→movimiento. Guarda un .png para el informe.

Uso (desde la raíz del repo):
    python herramientas/graficar_tiempos.py etapas.csv --salida desglose_tiempos.png

Formato del CSV de entrada (una fila por etapa):
    etapa,mediana_s
    Captura de audio,0.05
    Transcripcion en la nube,0.90
    Decision del modelo,0.42
    Espera en la cola,1.10
    Percepcion,0.08
    Cinematica inversa,0.12
    Planificacion,0.20
"""

import argparse
import csv
import os
import sys


def leer_etapas(ruta):
    """Devuelve (lista de etapas, lista de medianas en segundos) leídas del CSV."""
    etapas, valores = [], []
    with open(ruta, newline='', encoding='utf-8') as f:
        for fila in csv.reader(f):
            # Se saltan líneas vacías, comentarios y la cabecera
            if not fila or fila[0].lstrip().startswith('#') or fila[0].strip().lower() == 'etapa':
                continue
            if len(fila) < 2:
                continue
            try:
                valor = float(fila[1])
            except ValueError:
                continue
            etapas.append(fila[0].strip())
            valores.append(valor)
    return etapas, valores


def main():
    ap = argparse.ArgumentParser(description='Figura del desglose de tiempos (Pregunta 3)')
    ap.add_argument('csv', help='CSV con columnas etapa,mediana_s')
    ap.add_argument('--salida', default='desglose_tiempos.png', help='ruta del .png')
    args = ap.parse_args()

    if not os.path.isfile(args.csv):
        print(f'ERROR: no existe {args.csv}')
        return 2

    etapas, valores = leer_etapas(args.csv)
    if not etapas:
        print('ERROR: el CSV no tiene etapas válidas')
        return 1

    total = sum(valores) or 1.0

    # Tabla por consola, ordenada de mayor a menor
    for etapa, valor in sorted(zip(etapas, valores), key=lambda p: -p[1]):
        print(f'{etapa:30s} {valor * 1000:8.0f} ms   {100 * valor / total:5.1f} %')
    print(f'{"TOTAL":30s} {total * 1000:8.0f} ms   100.0 %')

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('AVISO: matplotlib no está instalado; se imprimió la tabla pero no la figura.')
        print('       Instálalo con: python -m pip install matplotlib')
        return 0

    porcentajes = [100 * v / total for v in valores]
    fig, ax = plt.subplots(figsize=(8, 5))
    barras = ax.barh(etapas, porcentajes, color='#4C72B0')
    ax.set_xlabel('% del tiempo voz → movimiento')
    ax.set_title('Desglose de tiempos (mediana por etapa)')
    ax.invert_yaxis()
    for barra, valor in zip(barras, valores):
        ax.text(barra.get_width() + 0.5, barra.get_y() + barra.get_height() / 2,
                f'{valor * 1000:.0f} ms', va='center', fontsize=9)
    fig.tight_layout()
    fig.savefig(args.salida, dpi=150)
    print(f'Figura guardada en {args.salida}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
