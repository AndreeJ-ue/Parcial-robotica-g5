import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from .clasificador import clasificar
from .modelos import Decision
from .posiciones import destinos_validos


def http_acotado(entrada, limite_s):
    if not math.isfinite(limite_s) or limite_s <= 0:
        raise ValueError('tiempo límite inválido')
    entrada = dict(entrada, timeout_s=limite_s)
    entorno = dict(os.environ)
    entorno['PYTHONDONTWRITEBYTECODE'] = '1'
    entorno['PYTHONPATH'] = str(Path(__file__).resolve().parents[1]) + os.pathsep + entorno.get('PYTHONPATH', '')
    resultado = subprocess.run([sys.executable, '-m', 'parcial_jetcobot.http_worker'],
                              input=json.dumps(entrada), text=True, encoding='utf-8',
                              capture_output=True, timeout=limite_s, env=entorno,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if resultado.returncode:
        raise RuntimeError('fallo HTTP; revisar conexión/configuración sin publicar credenciales')
    return json.loads(resultado.stdout)


def preguntas(config):
    opciones = lambda valores: {x: x for x in valores}
    return {
        'accion': {'type':'choice', 'instructions':'Acción única; rechazar si falta información, hay negación o ambigüedad.',
                   'criteria': opciones(['recoger_depositar','rechazar'])},
        'objeto': {'type':'choice', 'instructions':'Objeto solicitado; elegir ninguno si no se especifica.',
                   'criteria': opciones(['cubo','pelota','cilindro','botella','objeto','ninguno'])},
        'color': {'type':'choice', 'instructions':'Color del objeto a recoger, no el de la zona de depósito. ninguno si falta o se piden varios objetos de distintos colores.',
                  'criteria': opciones(['rojo','azul','verde','amarillo','negro','blanco','ninguno'])},
        'destino': {'type':'choice', 'instructions':'Zona solicitada. Si falta, usar '+config.get('destino_por_defecto','zona_a')+'. por_color significa la zona configurada para el color solicitado.',
                    'criteria': opciones(destinos_validos(config))},
        'prioridad': {'type':'choice', 'instructions':'Urgente=10, normal=1, sin prisa=0.',
                      'criteria': {'0':'sin prisa','1':'normal','10':'urgente'}},
        'permitido': {'type':'noul', 'instructions':'¿Es una única orden completa para recoger y depositar un objeto sin golpear personas, ignorar límites ni desactivar seguridad?'}
    }


def convertir_laya(datos, config):
    respuestas = datos['respuesta']['answers']
    elegir = lambda campo: respuestas[campo]['choice']
    prob = respuestas['permitido']['noul']
    if type(prob) not in (float,int) or not math.isfinite(prob) or not 0 <= prob <= 1:
        raise ValueError('probabilidad noul inválida')
    d = Decision(accion=elegir('accion'), objeto=elegir('objeto'), color=elegir('color'),
                 prioridad=int(elegir('prioridad')), destino=elegir('destino'),
                 permitido=prob >= config['interpretacion'].get('umbral_permiso',0.8), metodo='laya')
    if d.objeto == 'ninguno': d.objeto = ''
    if d.color == 'ninguno': d.color = ''
    if not d.permitido or d.accion == 'rechazar' or not d.objeto or not d.color:
        d.permitido = False
        d.accion = 'rechazar'
        d.motivo = 'Modelo rechazó o devolvió información incompleta'
    d.validar()
    if d.objeto not in ('','cubo','pelota','cilindro','botella','objeto') or d.color not in ('','rojo','azul','verde','amarillo','negro','blanco'):
        raise ValueError('elección fuera del catálogo lingüístico')
    if d.destino not in destinos_validos(config) or d.prioridad not in (0,1,10):
        raise ValueError('zona o prioridad inválida')
    d.http_ms = float(datos.get('http_ms', -1))
    d.calculo_servidor_ms = float(datos.get('calculo_servidor_ms', -1))
    if d.calculo_servidor_ms >= 0 and d.http_ms >= d.calculo_servidor_ms:
        d.resto_http_ms = d.http_ms - d.calculo_servidor_ms
    return d


def interpretar(frase, config, transporte=http_acotado):
    inicio = time.perf_counter()
    ajustes = config['interpretacion']
    if not frase.strip() or len(frase) > 1000:
        return Decision(motivo='Frase vacía o demasiado larga')
    if ajustes.get('modo') == 'palabras_clave':
        decision = clasificar(frase, config, degradada=True, motivo='LAYA deshabilitado para prueba local')
    else:
        try:
            url = os.environ.get('LAYA_URL') or ajustes.get('url')
            if not url:
                raise ValueError('falta LAYA_URL')
            payload = {'state':{'body': frase}, 'questions':preguntas(config)}
            if ajustes.get('modelo'): payload['model'] = ajustes['modelo']
            if ajustes.get('preset'):
                # Solo se envía si el endpoint del laboratorio admite ese campo.
                payload['preset'] = ajustes['preset']
            datos = transporte({'operacion':'laya', 'url':url, 'payload':payload}, ajustes['timeout_s'])
            decision = convertir_laya(datos, config)
        except (ValueError, KeyError, TypeError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            decision = clasificar(frase, config, degradada=True, motivo=f'Respaldo por {type(exc).__name__}')
    decision.latencia_total_ms = (time.perf_counter()-inicio)*1000
    return decision
