import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/jetcobot_p13'))
from jetcobot_p13.voz_google import transcribir, clave_desde_entorno, MODELO_POR_DEFECTO
if __name__ == '__main__':
    if len(sys.argv) < 2: raise SystemExit('Uso: python3 herramientas/transcribir_audio.py audio.wav [modelo]')
    texto, _, segundos = transcribir(sys.argv[1],clave_desde_entorno(),sys.argv[2] if len(sys.argv)>2 else MODELO_POR_DEFECTO,timeout_s=30)
    print(texto)
    print(f'Transcripción: {segundos:.3f} s')
