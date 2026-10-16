""" Nodo transcriptor_voz: de la voz al movimiento — Pregunta 3 del Parcial """

""" Antepone la transcripción a la cadena que ya existe: toma un audio (archivo .wav), lo
transcribe en español con Google AI Studio (Gemini) y entrega el texto al servicio
/interpretar_orden de la Pregunta 1. Si la nube no contesta dentro de timeout_transcripcion_s
o no hay internet, NO falla: avisa y pasa a MODO TEXTO POR TECLADO. El brazo nunca queda
esperando. Registra audio, transcripción y tiempos en transcripciones.csv """

import csv
import json
import os
import time

import rclpy
from rclpy.node import Node

from std_msgs.msg import String

from arm_broker_interfaces.srv import InterpretarOrden

from arm_broker import voz_google


class TranscriptorVoz(Node):

    def __init__(self):
        super().__init__('transcriptor_voz')

        # Parámetros de ROS 2: se pasan con --ros-args -p nombre:=valor
        self.declare_parameter('fuente', 'archivo')                  # archivo | teclado
        self.declare_parameter('ruta_audio', 'orden_01.wav')          # audio a transcribir
        self.declare_parameter('google_model', voz_google.MODELO_POR_DEFECTO)
        self.declare_parameter('timeout_transcripcion_s', 5.0)        # SU tiempo límite
        self.declare_parameter('modo_texto_tras_fallo', True)         # cae a teclado si falla
        self.declare_parameter('n_ordenes', 1)                        # cuántas órdenes procesa; <=0 = infinito
        self.declare_parameter('csv_transcripciones', 'transcripciones.csv')
        self.declare_parameter('topico_decision', 'orden_decidida')

        self.fuente = str(self.get_parameter('fuente').value)
        self.ruta_audio = str(self.get_parameter('ruta_audio').value)
        self.google_model = str(self.get_parameter('google_model').value)
        self.timeout_transcripcion = float(self.get_parameter('timeout_transcripcion_s').value)
        self.modo_texto_tras_fallo = bool(self.get_parameter('modo_texto_tras_fallo').value)
        self.n_ordenes = int(self.get_parameter('n_ordenes').value)
        self.csv_transcripciones = str(self.get_parameter('csv_transcripciones').value)

        # La clave va SOLO en variable de entorno; si falta, avisamos pero arrancamos igual
        self.api_key = voz_google.clave_desde_entorno()
        if not self.api_key:
            self.get_logger().warn(
                '⚠️  GOOGLE_API_KEY no está en el entorno: se usará MODO TEXTO POR TECLADO')

        # Cliente del servicio de la Pregunta 1 y publicador de la decisión hacia el orquestador
        self.cli = self.create_client(InterpretarOrden, 'interpretar_orden')
        self.pub_decision = self.create_publisher(
            String, str(self.get_parameter('topico_decision').value), 10)

        self._preparar_csv()

        self.get_logger().info('=' * 60)
        self.get_logger().info('  TRANSCRIPTOR_VOZ LISTO')
        self.get_logger().info(f'  fuente        : {self.fuente}')
        self.get_logger().info(f'  ruta_audio    : {self.ruta_audio}')
        self.get_logger().info(f'  modelo Google : {self.google_model}')
        self.get_logger().info(f'  timeout       : {self.timeout_transcripcion} s')
        self.get_logger().info('=' * 60)

    # 1. Registro de audio + transcripción (transcripciones.csv)
    def _preparar_csv(self):
        """Crea el CSV con su cabecera si no existe (no borra lo ya registrado)"""
        if not os.path.exists(self.csv_transcripciones):
            with open(self.csv_transcripciones, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([
                    't_unix', 'ruta_audio', 'texto_transcrito', 'metodo',
                    'tiempo_transcripcion_s', 'tiempo_decision_s', 't0', 't1', 't2', 't3',
                ])

    def _registrar(self, ruta_audio, texto, metodo, t_tr, t_dec, t0, t1, t2, t3):
        with open(self.csv_transcripciones, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                f'{time.time():.3f}', ruta_audio, texto, metodo,
                f'{t_tr:.3f}', f'{t_dec:.3f}',
                f'{t0:.3f}', f'{t1:.3f}', f'{t2:.3f}', f'{t3:.3f}',
            ])

    # 2. Captura + transcripción (con fallback a teclado)
    def _obtener_texto(self, indice):
        """Devuelve (texto, metodo, t0..t2). Si la nube falla y modo_texto_tras_fallo, lee teclado"""
        t0 = time.time()
        ruta = self.ruta_audio

        if self.fuente == 'archivo':
            # t1 = audio listo (el archivo ya existe: tiempo de lectura/escritura)
            t1 = time.time()
            try:
                texto, _crudo, t_tr = voz_google.transcribir(
                    ruta, self.api_key, self.google_model, self.timeout_transcripcion)
                t2 = time.time()
                if texto:
                    self.get_logger().info(f'✅ [GOOGLE] "{texto}" · {t_tr * 1000:.0f} ms')
                    return texto, 'google', t0, t1, t2
                raise RuntimeError('Gemini devolvió una transcripción vacía')
            except Exception as e:
                self.get_logger().warn(
                    f'⚠️  [TRANSCRIPTOR] sin respuesta de Google AI Studio en '
                    f'{self.timeout_transcripcion} s o error ({e!r})')
                if not self.modo_texto_tras_fallo:
                    raise

        # Modo texto: obligatorio cuando no hay internet o falló la transcripción
        t1 = time.time()
        self.get_logger().warn(
            '⚠️  MODO TEXTO POR TECLADO (el brazo NO queda esperando; '
            'escriba la orden a continuación)')
        texto = input(f'Escriba la orden {indice}: ').strip()
        return texto, 'teclado', t0, t1, time.time()

    # 3. Decisión: llamada al servicio /interpretar_orden (Pregunta 1)
    def _interpretar(self, frase):
        """Llama a /interpretar_orden y devuelve el Response; t3 = decisión recibida"""
        if not self.cli.wait_for_service(timeout_sec=10.0):
            self.get_logger().error('/interpretar_orden no aparece: ¿está corriendo interprete_ordenes?')
            return None, None
        req = InterpretarOrden.Request()
        req.frase = frase
        req.forzar_clasificador = False
        futuro = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, futuro)
        return futuro.result(), time.time()

    # 4. Publicación de la decisión para el orquestador (Pregunta 2)
    def _publicar_decision(self, frase, dec, t3):
        """Entrega la decisión tipada al orquestador por tópico, con los tiempos medidos"""
        msg = String()
        msg.data = json.dumps({
            'frase': frase,
            'accion': dec.accion,
            'objeto': dec.objeto,
            'color': dec.color,
            'prioridad': int(dec.prioridad),
            'permitido': bool(dec.permitido),
            'motivo': dec.motivo,
            'fuente': dec.fuente,
            'degradada': bool(dec.degradada),
            't3': t3,
        }, ensure_ascii=False)
        self.pub_decision.publish(msg)

    # 5. Ciclo principal
    def correr(self):
        infinito = self.n_ordenes <= 0
        indice = 1
        while rclpy.ok() and (infinito or indice <= self.n_ordenes):
            texto, metodo, t0, t1, t2 = self._obtener_texto(indice)

            if not texto:
                self.get_logger().warn(f'Orden {indice}: texto vacío, se ignora')
                indice += 1
                continue

            dec, t3 = self._interpretar(texto)
            if dec is None:
                indice += 1
                continue

            t_dec = t3 - t2
            self.get_logger().info(
                f'🧭 [DECISIÓN] {dec.accion}/{dec.objeto}/{dec.color} '
                f'p={dec.prioridad} permitido={dec.permitido} · decisión {t_dec * 1000:.0f} ms')

            self._publicar_decision(texto, dec, t3)
            self._registrar(self.ruta_audio, texto, metodo, t2 - t1, t_dec, t0, t1, t2, t3)
            indice += 1


def main(args=None):
    rclpy.init(args=args)
    nodo = TranscriptorVoz()
    try:
        nodo.correr()
    except KeyboardInterrupt:
        pass
    finally:
        nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
