import mimetypes
from pathlib import Path
from .interpretacion import http_acotado


def transcribir(audio,limite_s=12.0,transporte=http_acotado):
    ruta=Path(audio)
    if not ruta.is_file():raise ValueError('No existe el audio')
    mime={'.wav':'audio/wav','.mp3':'audio/mpeg','.flac':'audio/flac','.ogg':'audio/ogg'}.get(ruta.suffix.lower())
    if not mime:raise ValueError('Formato de audio no admitido por este cliente')
    datos=transporte({'operacion':'gemini','audio':str(ruta.resolve()),'mime':mime},limite_s)
    partes=datos['respuesta']['candidates'][0]['content']['parts']
    texto=' '.join(p['text'] for p in partes if 'text' in p).strip()
    if not texto:raise ValueError('La transcripción está vacía')
    return texto
