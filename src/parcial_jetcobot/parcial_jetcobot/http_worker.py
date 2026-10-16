"""HTTP en proceso aislado: el padre impone un plazo total y termina el proceso."""
import base64
import json
import os
import re
import sys
import time
import urllib.request


def main():
    entrada = json.load(sys.stdin)
    headers = {'Content-Type': 'application/json'}
    if entrada['operacion'] == 'laya':
        url = entrada['url']
        payload = entrada['payload']
        clave = os.environ.get('LAYA_API_KEY', '')
        if clave:
            headers['Authorization'] = 'Bearer ' + clave
    elif entrada['operacion'] == 'gemini':
        modelo = os.environ.get('GEMINI_MODEL', '')
        clave = os.environ.get('GEMINI_API_KEY', '')
        if not clave or not re.fullmatch(r'[a-zA-Z0-9._-]+', modelo):
            raise ValueError('Falta GEMINI_API_KEY o GEMINI_MODEL válido')
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent'
        headers['x-goog-api-key'] = clave
        with open(entrada['audio'], 'rb') as archivo:
            contenido = archivo.read(16*1024*1024 + 1)
        if len(contenido) > 16*1024*1024:
            raise ValueError('Audio excede el límite local de 16 MiB')
        payload = {'contents': [{'parts': [
            {'text': 'Transcribe literalmente este audio en español. Devuelve solo la transcripción.'},
            {'inlineData': {'mimeType': entrada['mime'], 'data': base64.b64encode(contenido).decode()}}]}]}
    else:
        raise ValueError('operación desconocida')
    req = urllib.request.Request(url, json.dumps(payload).encode(), headers=headers)
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=entrada['timeout_s']) as respuesta:
        datos = respuesta.read(2*1024*1024 + 1)
        if len(datos) > 2*1024*1024:
            raise ValueError('Respuesta excesiva')
        # El servidor oficial incluye infer; otras versiones pueden no hacerlo.
        server_timing = respuesta.headers.get('Server-Timing', '')
        infer_header = respuesta.headers.get('X-Inference-Time-Ms', '')
    http_ms = (time.perf_counter() - t0)*1000
    coincidencia = re.search(r'(?:infer|inference);dur=([0-9.]+)', server_timing)
    print(json.dumps({'respuesta': json.loads(datos), 'http_ms': http_ms,
                      'calculo_servidor_ms': float(infer_header) if infer_header else (float(coincidencia[1]) if coincidencia else -1.0)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # No volcar URLs, cabeceras, credenciales ni el cuerpo de errores HTTP.
        print(json.dumps({'error': type(exc).__name__}), file=sys.stderr)
        sys.exit(1)
