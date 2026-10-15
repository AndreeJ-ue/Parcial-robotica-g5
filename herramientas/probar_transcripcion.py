""" Prueba de la transcripción de Google AI Studio SIN ROS 2 — Pregunta 3 """

""" Se corre PRIMERO, antes de tocar el nodo transcriptor_voz, para confirmar que la clave, el
modelo (gemini-2.5-flash) y el endpoint funcionan. Imprime la transcripción y los metadatos.

Uso (desde la raíz del repo):
    python herramientas/probar_transcripcion.py orden.wav
    python herramientas/probar_transcripcion.py orden.wav gemini-2.5-flash

La clave se lee SIEMPRE de la variable de entorno GOOGLE_API_KEY (nunca en el código). """

import os
import sys

# Deja importable el paquete copiado a herramientas/ (sube a src/arm_broker)
_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_raiz, 'src', 'arm_broker'))

from arm_broker import voz_google


def main():
    if len(sys.argv) < 2:
        print('Uso: python herramientas/probar_transcripcion.py <audio.wav> [modelo]')
        return 2

    ruta = sys.argv[1]
    modelo = sys.argv[2] if len(sys.argv) > 2 else voz_google.MODELO_POR_DEFECTO

    clave = voz_google.clave_desde_entorno()
    if not clave:
        print('ERROR: falta la variable de entorno GOOGLE_API_KEY')
        print('  PowerShell : $env:GOOGLE_API_KEY = "AIza..."')
        print('  bash/Jetson: export GOOGLE_API_KEY="AIza..."')
        return 2

    print(f'Audio   : {ruta}')
    print(f'Modelo  : {modelo}')
    print('Consultando a Google AI Studio...')

    try:
        texto, _crudo, dt = voz_google.transcribir(ruta, clave, modelo, timeout_s=30.0)
    except Exception as e:
        print(f'ERROR al transcribir: {e!r}')
        return 1

    print('-' * 60)
    print(f'Transcripción ({dt * 1000:.0f} ms): {texto!r}')
    print('-' * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
