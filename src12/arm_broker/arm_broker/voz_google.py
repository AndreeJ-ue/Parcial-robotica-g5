""" Cliente HTTP hacia Google AI Studio (Gemini) para transcribir audio — Pregunta 3 """

""" Google AI Studio NO es un nodo ROS 2: se habla por HTTPS con una clave que va SOLO en la
variable de entorno GOOGLE_API_KEY (nunca en el código ni en el repositorio). Este módulo es
la única pieza que conoce HTTP; el nodo transcriptor_voz.py no sabe cómo se pide la transcripción """

import base64
import os
import time

import requests

MODELO_POR_DEFECTO = 'gemini-3.8-flash'
URL_BASE = 'https://generativelanguage.googleapis.com/v1beta/models'

PROMPT = ('Transcribe exactamente lo que se dice en español. '
          'Devuelve únicamente la transcripción, sin comillas ni comentarios.')

_MIMES = {
    '.wav': 'audio/wav',
    '.mp3': 'audio/mp3',
    '.m4a': 'audio/mp4',
    '.mp4': 'audio/mp4',
    '.aac': 'audio/aac',
    '.ogg': 'audio/ogg',
    '.flac': 'audio/flac',
    '.webm': 'audio/webm',
}


def clave_desde_entorno():
    """Lee la clave de Google AI Studio del entorno (nunca del código)"""
    return os.environ.get('GOOGLE_API_KEY', '').strip()


def _mime_de(ruta):
    """Deduce el tipo MIME del audio por su extensión (Gemini lee wav, mp3, m4a, etc.)"""
    return _MIMES.get(os.path.splitext(ruta)[1].lower(), 'audio/wav')


def _leer_audio_base64(ruta):
    """Lee el archivo de audio y lo codifica en base64, que es como Gemini recibe el inline_data"""
    with open(ruta, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')


def _extraer_texto(cuerpo):
    """Saca la transcripción de candidates[0].content.parts[*].text y limpia espacios"""
    try:
        partes = cuerpo['candidates'][0]['content']['parts']
    except (KeyError, IndexError, TypeError):
        return ''
    trozos = [p.get('text', '') for p in partes if isinstance(p, dict)]
    return ' '.join(t for t in trozos if t).strip()


def transcribir(ruta_audio, api_key, modelo=MODELO_POR_DEFECTO, timeout_s=5.0):
    """Transcribe un archivo de audio a texto en español usando Google AI Studio.

    Parámetros:
      ruta_audio  ruta a un .wav/.mp3/.m4a (PCM 16 kHz mono funciona bien)
      api_key     clave de Google AI Studio (leerla de GOOGLE_API_KEY)
      modelo      nombre del modelo; por defecto gemini-3.8-flash
      timeout_s   SU tiempo límite: si no llega a tiempo lanza Timeout (requests)

    Retorna (texto, respuesta_cruda_json, tiempo_s).
    Lanza excepción si hay timeout, error HTTP, sin red o JSON inválido: quien llama decide
    caer al modo texto por teclado, de modo que el brazo nunca quede esperando.
    """
    if not api_key:
        raise RuntimeError('Falta GOOGLE_API_KEY en el entorno (no hay transmisión disponible)')
    if not os.path.isfile(ruta_audio):
        raise FileNotFoundError(f'No existe el archivo de audio: {ruta_audio}')

    payload = {
        'contents': [{
            'parts': [
                {'text': PROMPT},
                {'inline_data': {'mime_type': _mime_de(ruta_audio),
                                 'data': _leer_audio_base64(ruta_audio)}},
            ]
        }]
    }
    url = f'{URL_BASE}/{modelo}:generateContent'

    t0 = time.time()
    r = requests.post(
        url,
        headers={'x-goog-api-key': api_key, 'content-type': 'application/json'},
        json=payload,
        timeout=timeout_s,
    )
    r.raise_for_status()
    cuerpo = r.json()
    return _extraer_texto(cuerpo), cuerpo, time.time() - t0
