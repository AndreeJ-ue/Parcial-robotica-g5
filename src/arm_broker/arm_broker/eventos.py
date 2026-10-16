"""Registro CSV incremental: tiempos monotónicos para duraciones y UTC para fecha."""
import csv
import pathlib
import threading
import time


CAMPOS = ['wall_time_ns', 'monotonic_s', 'evento', 'goal_id', 'client_id',
          'priority', 'motivo', 'wait_time_s', 'exec_time_s']


class RegistroEventos:
    def __init__(self, ruta):
        self.lock = threading.Lock()
        self.archivo = None
        if ruta:
            destino = pathlib.Path(ruta).expanduser()
            destino.parent.mkdir(parents=True, exist_ok=True)
            nuevo = not destino.exists() or destino.stat().st_size == 0
            self.archivo = destino.open('a', newline='', encoding='utf-8')
            self.writer = csv.DictWriter(self.archivo, fieldnames=CAMPOS)
            if nuevo:
                self.writer.writeheader()
                self.archivo.flush()

    def registrar(self, evento, goal_id='', client_id='', priority=0, motivo='',
                  wait_time_s=0.0, exec_time_s=0.0):
        if self.archivo is None:
            return
        fila = dict(zip(CAMPOS, [time.time_ns(), time.monotonic(), evento, goal_id,
                               client_id, priority, motivo, wait_time_s, exec_time_s]))
        with self.lock:
            self.writer.writerow(fila)
            self.archivo.flush()

    def cerrar(self):
        with self.lock:
            if self.archivo:
                self.archivo.close()
                self.archivo = None
