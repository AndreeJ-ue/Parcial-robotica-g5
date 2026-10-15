""" Percepción por cámara: qué color hay en cada posición de la mesa — Ítem 2 """

""" La cámara detecta los cubos por máscara HSV (los mismos rangos de color del problema 5) y
asigna cada cubo a una de las cuatro posiciones usando ANCLAS de píxel calibradas. Con eso se
construye en vivo el mapa color -> 'pos1'..'pos4', porque el color de cada esquina NO se conoce
de antemano.

El nodo orquestador llama a esperar_color(color, timeout) y recibe la posición estable, o None
si el color pedido no está sobre la mesa. Esta clase NUNCA publica en ROS: solo mira video. """

import threading
import time

try:
    import cv2 as cv
    CV_DISPONIBLE = True
except ImportError:
    CV_DISPONIBLE = False

# 1. Rangos HSV por color (tomados del problema 5; ROJO lleva dos franjas por el tono 0/180)
COLORES = {
    'rojo': [((0, 120, 70), (10, 255, 255)), ((170, 120, 70), (180, 255, 255))],
    'amarillo': [((20, 100, 100), (35, 255, 255))],
    'verde': [((40, 70, 70), (85, 255, 255))],
    'azul': [((90, 100, 70), (130, 255, 255))],
}

AREA_MINIMA = 300.0
FRAMES_ESTABILIDAD = 8
ANCHO_FRAME = 640
ALTO_FRAME = 480


class PercepcionCamara:
    """Detecta colores y los asigna a posiciones según anclas de píxel."""

    def __init__(self, anclas=None, radio_ancla=70.0, indice_camara=None,
                 frames_estabilidad=FRAMES_ESTABILIDAD, area_minima=AREA_MINIMA):
        self.anclas = dict(anclas or {})
        if not self.anclas:
            self.anclas = {
                'pos1': (240.0, 180.0),
                'pos2': (240.0, 340.0),
                'pos3': (400.0, 180.0),
                'pos4': (400.0, 340.0),
            }
        self.radio_ancla = float(radio_ancla)
        self.indice_camara = indice_camara
        self.frames_estabilidad = int(frames_estabilidad)
        self.area_minima = float(area_minima)

        self.lock = threading.Lock()
        self.mapa = {}
        self.detecciones = []
        self._ultimo_frame = None
        self.disponible = bool(CV_DISPONIBLE)
        self._activa = threading.Event()
        self._cap = None
        self._hilo = None

    # 2. Apertura de cámara
    def abrir(self):
        """Abre la primera cámara que entregue imagen; devuelve True si lo logra."""
        if not CV_DISPONIBLE:
            print('[CAMARA] OpenCV no está disponible: sin percepción')
            self.disponible = False
            return False
        indices = [self.indice_camara] if self.indice_camara is not None else [0, 1, 2, 3]
        for indice in indices:
            cap = cv.VideoCapture(indice)
            if cap.isOpened():
                cap.set(cv.CAP_PROP_FRAME_WIDTH, ANCHO_FRAME)
                cap.set(cv.CAP_PROP_FRAME_HEIGHT, ALTO_FRAME)
                ok, _ = cap.read()
                if ok:
                    self._cap = cap
                    self.indice_camara = indice
                    self.disponible = True
                    print(f'[CAMARA] abierta en índice {indice}')
                    return True
            cap.release()
        self.disponible = False
        print('[CAMARA] no se encontró cámara disponible')
        return False

    # 3. Hilo de captura
    def iniciar(self):
        """Arranca la captura en su propio hilo (cámara fija sobre la mesa)."""
        if not self.abrir():
            return False
        self._activa.set()
        self._hilo = threading.Thread(target=self._hilo_captura, daemon=True)
        self._hilo.start()
        return True

    def detener(self):
        self._activa.clear()
        if self._hilo is not None:
            self._hilo.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()

    def _hilo_captura(self):
        try:
            while self._activa.is_set():
                ok, frame = self._cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                detecciones = self._detectar(frame)
                mapa = self._asignar_posiciones(detecciones)
                with self.lock:
                    self.detecciones = detecciones
                    self.mapa = mapa
                    self._ultimo_frame = frame
        finally:
            if self._cap is not None:
                self._cap.release()

    # 4. Detección de color
    @staticmethod
    def _mascara_color(hsv, rangos):
        total = None
        for bajo, alto in rangos:
            m = cv.inRange(hsv, bajo, alto)
            total = m if total is None else cv.bitwise_or(total, m)
        return total

    def _detectar(self, frame):
        """Devuelve [(color, cx, cy), ...] con el blob de mayor área por color."""
        hsv = cv.cvtColor(frame, cv.COLOR_BGR2HSV)
        kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (5, 5))
        resultado = []
        for nombre, rangos in COLORES.items():
            mascara = self._mascara_color(hsv, rangos)
            mascara = cv.morphologyEx(mascara, cv.MORPH_OPEN, kernel)
            mascara = cv.morphologyEx(mascara, cv.MORPH_CLOSE, kernel)
            contornos, _ = cv.findContours(mascara, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
            if not contornos:
                continue
            contorno = max(contornos, key=cv.contourArea)
            if cv.contourArea(contorno) < self.area_minima:
                continue
            m = cv.moments(contorno)
            if m['m00'] == 0:
                continue
            cx = int(m['m10'] / m['m00'])
            cy = int(m['m01'] / m['m00'])
            resultado.append((nombre, cx, cy))
        return resultado

    # 5. Asignación a posiciones por ancla más cercana
    def _asignar_posiciones(self, detecciones):
        """Mapa color -> posición usando la ancla dentro de radio_ancla más cercana."""
        mapa = {}
        for color, cx, cy in detecciones:
            mejor, dist_mejor = None, None
            for posicion, (ax, ay) in self.anclas.items():
                dist = ((cx - ax) ** 2 + (cy - ay) ** 2) ** 0.5
                if dist <= self.radio_ancla and (dist_mejor is None or dist < dist_mejor):
                    mejor, dist_mejor = posicion, dist
            if mejor is not None:
                mapa[color] = mejor
        return mapa

    # 6. Consulta desde el orquestador
    def mapa_actual(self):
        with self.lock:
            return dict(self.mapa)

    def leer_frame(self):
        """Devuelve una copia del último frame capturado (o None). Útil para ver/guardar."""
        with self.lock:
            return None if self._ultimo_frame is None else self._ultimo_frame.copy()

    def esperar_color(self, color, timeout_s=8.0):
        """Espera detección ESTABLE del color y devuelve su posición, o None al agotar el tiempo."""
        color = str(color).lower()
        t0 = time.time()
        estable, conteo = None, 0
        while time.time() - t0 < timeout_s:
            posicion = self.mapa_actual().get(color)
            if posicion is not None and posicion == estable:
                conteo += 1
            else:
                estable, conteo = posicion, 1
            if posicion is not None and conteo >= self.frames_estabilidad:
                return posicion
            time.sleep(0.05)
        return None
