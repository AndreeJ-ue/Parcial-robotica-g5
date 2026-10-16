import json
import shutil
import subprocess
import time
import uuid
import wave
from pathlib import Path
import rclpy
from .cliente import ClienteOrdenes
from .transcripcion import transcribir


def capturar(ruta,duracion):
    import sounddevice as sd
    import numpy as np
    fs=16000;inicio=time.time_ns()
    muestras=sd.rec(int(duracion*fs),samplerate=fs,channels=1,dtype='int16')
    sd.wait()
    with wave.open(str(ruta),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(fs);f.writeframes(muestras.tobytes())
    return inicio,time.time_ns()


def main():
    rclpy.init();nodo=None
    try:
        nodo=ClienteOrdenes('transcriptor_voz')
        for k,v in {'archivo_audio':'','duracion_audio_s':5.0,'fin_habla_offset_s':-1.0,
                    'timeout_transcripcion_s':12.0}.items():nodo.declare_parameter(k,v)
        carpeta=Path('evidencias/audio');carpeta.mkdir(parents=True,exist_ok=True)
        original=nodo.get_parameter('archivo_audio').value
        ruta=carpeta/(uuid.uuid4().hex+(Path(original).suffix if original else '.wav'))
        datos={'audio':str(ruta),'fin_habla_confirmado':False}
        try:
            if original:
                shutil.copy2(original,ruta)
                inicio=0;fin_captura=time.time_ns()
            else:
                print('Grabando. No se enviará movimiento hasta terminar la transcripción e interpretación.')
                inicio,fin_captura=capturar(ruta,nodo.get_parameter('duracion_audio_s').value)
            offset=nodo.get_parameter('fin_habla_offset_s').value
            datos['inicio_captura_wall_ns']=inicio
            datos['fin_captura_wall_ns']=fin_captura
            fin_habla=inicio+int(offset*1e9) if inicio and 0<=offset<=nodo.get_parameter('duracion_audio_s').value else 0
            datos['fin_habla_confirmado']=bool(fin_habla)
            datos['captura_post_habla_s']=(fin_captura-fin_habla)/1e9 if fin_habla else None
            t0=time.perf_counter()
            texto=transcribir(ruta,nodo.get_parameter('timeout_transcripcion_s').value)
            datos.update(transcripcion_s=time.perf_counter()-t0,transcripcion=texto,modo='voz')
        except (RuntimeError,ValueError,KeyError,IndexError,OSError,ImportError,subprocess.TimeoutExpired) as exc:
            datos.update(modo='teclado',motivo=f'Transcripción no disponible: {type(exc).__name__}')
            print(datos['motivo']+'. Modo texto activo.')
            texto=input('Escribe la orden: ');fin_habla=0
        resultado=nodo.procesar(texto,fin_habla,datos)
        ruta.with_suffix(ruta.suffix+'.json').write_text(json.dumps(resultado,ensure_ascii=False,indent=2),encoding='utf-8')
    except (KeyboardInterrupt,EOFError):pass
    finally:
        if nodo:nodo.destroy_node()
        if rclpy.ok():rclpy.shutdown()
